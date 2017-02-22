#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import os
import threading
import time
import traceback
from multiprocessing import Process, Pipe
from threading import Thread

from pika.exceptions import ConnectionClosed

from itsbox.operator import Config
from itsbox.operator.ThreadPool import TaskThreadPool
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')


class WorkerProcess(Process):
    readyFlag = False
    stoppingFlag = False
    exitFlag = False
    threadCount = 0
    receivedCount = 0
    threadPool = None
    parentPipe = None
    childPipe = None
    pipeReceiver = None
    queue = None
    sendEvent = threading.Event()
    endEvent = threading.Event()

    def __init__(self, thread_count=10):
        logger.debug('Worker instance is creating...')
        self.parentPipe, self.childPipe = Pipe()
        Process.__init__(self, target=self.start_process, args=(self.childPipe,))
        self.daemon = True
        self.threadCount = thread_count
        logger.debug('Worker instance has been successfully created : ThreadCount=%d' % thread_count)

    def create_mq_connection_and_channel(self):
        self.queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.queue.create_receive_channel(Config.RABBITMQ_QNAME_MSG_IN, durable=True)

    def on_message(self, channel, method, properties, message):
        self.receivedCount += 1
        message = message.decode('utf-8') if type(message) is bytes else message
        message = message.strip()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Worker received a message from queue : Message=\'%s\'' % message.replace('\r', '\\r').replace('\n', '\\n'))
        self.threadPool.add_task(message)

    def start_process(self, child_pipe):
        logger.debug('Starting the worker process : PID=%d' % self.pid)
        self.childPipe = child_pipe
        self.threadPool = TaskThreadPool(self.threadCount)
        self.pipeReceiver = PipeReceiver(self)
        self.create_mq_connection_and_channel()
        self.childPipe.send({ 'pid':self.pid, 'message':'Starting the worker was completed.' })
        while self.exitFlag is False:
            logger.info('Worker starts consuming the queue : Queue=%s' % Config.RABBITMQ_QNAME_MSG_IN)
            try:
                self.queue.start_receive(self.on_message, no_ack=True)
            except ConnectionClosed:
                logger.warn('Queue receive channel for message is closed. reconnecting... : Queue=%s' % Config.RABBITMQ_QNAME_MSG_IN)
                self.create_mq_connection_and_channel()
            except BaseException as e:
                error_logger.exception('Exception occurred during consuming the queue.')
                logger.error('Exception occurred during consuming the queue : Queue=%s, Exception=%s' % (Config.RABBITMQ_QNAME_MSG_IN, e))
            time.sleep(1)
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
        remain_task_count = self.threadPool.jobQueue.qsize()
        if remain_task_count > 0:
            logger.warn('Tasks remain in the internal queue. It will be lost : RemainTaskCount=%d' % remain_task_count)
        logger.debug('Worker has been stopped.')

    def stop(self):
        logger.info('The worker has been requested to stop.')
        self.exitFlag = True
        if self.queue:
            self.queue.stop_receive()
        if self.threadPool:
            self.threadPool.stop_task(wait=True)
        self.endEvent.set()
        logger.info('The worker was successfully stopped.')


class PipeReceiver(Thread):
    exitFlag = False
    worker = None

    def __init__(self, worker):
        Thread.__init__(self)
        self.worker = worker
        self.daemon = True
        logger.debug('PipeReceiver instance has been created : Pipe=%s' % str(worker.childPipe))
        self.start()

    def run(self):
        logger.debug('PipeReceiver is starting...')
        while self.exitFlag is False:
            try:
                response_dict = {}
                if self.worker.childPipe.poll(None):
                    request_dict = self.worker.childPipe.recv()
                    logger.debug('PipeReceiver received request from manager pipe : Message=\'%s\'' % request_dict)
                    if request_dict is None or request_dict.get('hash') is None:
                        raise SyntaxError('Invalid request data in PipeReceiver.')
                    response_dict['hash'] = request_dict.get('hash')
                    response_dict['pid'] = os.getpid()
                    command = request_dict.get('command')
                    option = request_dict.get('option')
                    if command == 'get_worker_info':
                        response_dict['active_tasks'] = self.worker.threadPool.get_active_tasks()
                        response_dict['status'] = 'Unknown'
                        response_dict['thread'] = { 'total':len(self.worker.threadPool.threads),
                                                    'active':len(response_dict['active_tasks']),
                                                    'idle':len(self.worker.threadPool.threads)-len(response_dict['active_tasks']) }
                        if response_dict['thread']['idle'] == 0:
                            response_dict['status'] = 'Full'
                        elif response_dict['thread']['active'] > 0:
                            response_dict['status'] = 'Active'
                        else:
                            response_dict['status'] = 'Idle'
                        response_dict['queued'] = self.worker.threadPool.jobQueue.qsize()
                        process, success, fail, reply = self.worker.threadPool.get_processed_count()
                        response_dict['count'] = { 'receive':self.worker.receivedCount, 'process':process, 'success':success, 'fail':fail, 'reply':reply }
                    elif command == 'stop_worker':
                        self.worker.stop()
                        response_dict['message'] = 'The worker has been gracefully stopped.'
                        self.exitFlag = True
                    else:
                        response_dict['message'] = 'Unknown command'
            except BaseException as e:
                error_logger.exception('Exception occurred during processing data from manager.')
                logger.error('Exception occurred during processing data from manager : Exception=%s' % e)
            finally:
                self.worker.childPipe.send(response_dict)
                logger.debug('PipeReceiver sent response to manager pipe : Message=\'%s\'' % response_dict)
                self.worker.sendEvent.set()
        logger.debug('PipeReceiver has been stopped.')
