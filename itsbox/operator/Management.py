#!/usr/bin/python
#-*- coding: utf-8 -*-
import json
import logging
import os
import threading
import time
from multiprocessing import Process, Pipe
from threading import Thread

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
from concurrent.futures import ThreadPoolExecutor
from pika.exceptions import ConnectionClosed

from itsbox.operator import Config
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')

clients = {}


def add_client_id(message, client_id):
    dict_data = json.loads(message)
    dict_data['client_channel_id'] = client_id
    return json.dumps(dict_data)


def extract_client_id(message):
    dict_data = json.loads(message)
    client_id = dict_data.get('client_channel_id')
    return client_id, message


def write_to_client(client_id, message):
    global clients
    handler = clients.get(client_id)
    if handler:
        handler.write_message(json.dumps(json.loads(message), indent=2))
        logger.debug('Sent message to WebSocket client : ClientId=%d, Message=%s' % (client_id, message))
    else:
        logger.warn('Not found client key in list. The client may be closed : ClientID=%s' % client_id)


class WebsocketMgmtServer(Process):
    readyFlag = False
    stoppingFlag = False
    httpServer = None
    mgmtQueueListener = None
    parentPipe = None
    childPipe = None
    pipeReceiver = None
    sendEvent = threading.Event()
    endEvent = threading.Event()

    def __init__(self, thread_count=10):
        logger.debug('Management instance is creating...')
        self.parentPipe, self.childPipe = Pipe()
        Process.__init__(self, target=self.start_process, args=(self.childPipe,))
        self.daemon = True
        logger.debug('Management instance has been successfully created.')

    def start_process(self, child_pipe):
        logger.debug('Started the management process : PID=%d' % self.pid)
        self.childPipe = child_pipe
        self.pipeReceiver = PipeReceiver(self)
        self.httpServer = tornado.httpserver.HTTPServer(MgmtApplication())
        self.httpServer.listen(Config.WEBSOCKET_MGMT_SERVER_PORT)
        logger.info('Listening to the WebSocket server port for processing management request : Port=%d' % Config.WEBSOCKET_MGMT_SERVER_PORT)
        self.mgmtQueueListener = MgmtQueueListener()
        self.childPipe.send({ 'pid':self.pid, 'message':'Starting the management was completed.' })
        try:
            tornado.ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            pass
        if not self.sendEvent.isSet():
            logger.debug('Waiting until the worker responds to manager')
            try:
                self.sendEvent.wait()
            except KeyboardInterrupt:
                pass
        if not self.endEvent.isSet():
            logger.debug('Waiting until stop process finishes.')
            try:
                self.endEvent.wait()
            except KeyboardInterrupt:
                pass
        logger.debug('Manager has been stopped.')

    def stop(self):
        logger.debug('The Management has been requested to stop.')
        self.mgmtQueueListener.stop()
        tornado.ioloop.IOLoop.instance().add_callback(tornado.ioloop.IOLoop.instance().stop)
        self.httpServer.close_all_connections()
        self.httpServer.stop()
        self.endEvent.set()
        logger.debug('The Management was successfully stopped.')


class PipeReceiver(Thread):
    exitFlag = False
    wsMgmtServer = None

    def __init__(self, mgmt):
        Thread.__init__(self)
        self.wsMgmtServer = mgmt
        self.daemon = True
        logger.debug('PipeReceiver instance has been created : Pipe=%s' % str(mgmt.childPipe))
        self.start()

    def run(self):
        logger.debug('PipeReceiver is starting...')
        while self.exitFlag is False:
            try:
                response_dict = {}
                if self.wsMgmtServer.childPipe.poll(None):
                    request_dict = self.wsMgmtServer.childPipe.recv()
                    logger.debug('PipeReceiver received request from manager pipe : Message=\'%s\'' % request_dict)
                    if request_dict is None or request_dict.get('hash') is None:
                        raise SyntaxError('Invalid request data in PipeReceiver.')
                    response_dict['hash'] = request_dict.get('hash')
                    response_dict['pid'] = os.getpid()
                    command = request_dict.get('command')
                    option = request_dict.get('option')
                    if command == 'stop_management':
                        self.wsMgmtServer.stop()
                        response_dict['message'] = 'The management has been stopped.'
                        self.exitFlag = True
                    else:
                        response_dict['message'] = 'Unknown command'
            except BaseException as e:
                error_logger.exception('Exception occurred during processing data from manager')
                logger.error('Exception occurred during processing data from manager : Exception=%s' % e)
            finally:
                self.wsMgmtServer.childPipe.send(response_dict)
                logger.debug('PipeReceiver sent response to manager pipe : Message=\'%s\'' % response_dict)
                self.wsMgmtServer.sendEvent.set()
        logger.debug('PipeReceiver has been stopped.')


class MgmtApplication(tornado.web.Application):
    def __init__(self):
        handlers = [(r'/operator/mgmt', MgmtWebsocketHandler)]
        tornado.web.Application.__init__(self, handlers)


class MgmtWebsocketHandler(tornado.websocket.WebSocketHandler):
    threadPoolExecutor = ThreadPoolExecutor(max_workers=Config.MAX_THREAD_PER_WORKER/2)
    queue = None
    clientId = None

    @staticmethod
    def create_mq_connection_and_channel():
        MgmtWebsocketHandler.queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        MgmtWebsocketHandler.queue.create_send_channel(Config.RABBITMQ_QNAME_MGMT_IN, durable=True)

    def check_origin(self, origin):
        return True

    def open(self):
        if MgmtWebsocketHandler.queue is None:
            MgmtWebsocketHandler.create_mq_connection_and_channel()
        self.clientId = id(self)
        global clients
        clients[self.clientId] = self
        logger.info('WebSocket client has been registered : ClientID=%s, TotalClients=%d' % (self.clientId, len(clients)))

    def data_received(self, chunk):
        pass

    def on_message(self, message):
        try:
            dict_data = json.loads(message)
            if dict_data is not None and dict_data.get('op_action') == 'stop' and dict_data.get('op_target') == 'management':
                dict_data['direction'] = 2
                dict_data['success'] = 1
                dict_data['msg'] = 'Stopping the management will be done asynchronously.'
                write_to_client(self.clientId, json.dumps(dict_data))
        except Exception as e:
            error_logger('Exception occurred during parsing received data.')
            logger.warn('Exception occurred during parsing received data : Exception=%s, Message=%s' % (e, message))
        MgmtWebsocketHandler.threadPoolExecutor.submit(self.send_message_to_queue, message)

    def send_message_to_queue(self, message):
        message = message.decode('utf-8') if type(message) is bytes else message
        message = message.strip()
        logger.debug('Received message from WebSocket client : ClientId=%d, Message=%s' % (self.clientId, message.replace('\r', '\\r').replace('\n', '\\n')))
        message_with_client_id = add_client_id(message, self.clientId)
        while True:
            try:
                self.queue.send(message_with_client_id)
                logger.debug('Sent request to the inbound management queue : Message=%s' % message_with_client_id)
                break
            except ConnectionClosed:
                logger.warn('Queue send channel for management is closed. reconnecting... : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_IN)
                self.create_mq_connection_and_channel()
                time.sleep(1)

    def on_close(self):
        global clients
        if clients.get(self.clientId):
            del clients[self.clientId]
        logger.info('WebSocket client has been closed : ClientID=%s, TotalClients=%d' % (self.clientId, len(clients)))


class MgmtQueueListener(Thread):
    exitFlag = False
    queue = None

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.create_mq_connection_and_channel()
        logger.debug('MgmtQueueListener instance has been created : Name=\'%s\'' % self.name)
        self.start()

    def create_mq_connection_and_channel(self):
        self.queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.queue.create_receive_channel(Config.RABBITMQ_QNAME_MGMT_OUT, durable=True)

    def run(self):
        while self.exitFlag is False:
            logger.info('Worker starts consuming the queue : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_OUT)
            try:
                self.queue.start_receive(self.on_message, no_ack=True)
            except ConnectionClosed:
                logger.warn('Queue receive channel for management is closed. reconnecting... : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_OUT)
                self.create_mq_connection_and_channel()
            except BaseException as e:
                error_logger.exception('Exception occurred during consuming the queue.')
                logger.error('Exception occurred during consuming the queue : Queue=%s, Exception=%s' % (Config.RABBITMQ_QNAME_MGMT_OUT, e))
            time.sleep(1)

    def on_message(self, channel, method, properties, message):
        message = message.decode('utf-8') if type(message) is bytes else message
        message = message.strip()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Management received a message from queue : Message=\'%s\'' % message.replace('\r', '\\r').replace('\n', '\\n'))
        client_id, message_to_return = extract_client_id(message)
        Thread(target=write_to_client, args=(client_id, message_to_return)).start()

    def stop(self):
        self.exitFlag = True
        if self.queue:
            self.queue.stop_receive()

