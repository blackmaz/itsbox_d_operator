#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import time
import traceback
from threading import Thread

from pika.exceptions import ConnectionClosed

from itsbox.operator import Config
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
access_logger = logging.getLogger('access')
access_logger.setLevel(logging.DEBUG)
error_logger = logging.getLogger('error')


class AbstractThread(Thread):
    exitFlag = False
    runFlag = False
    startTime = 0
    processedCount = 0
    successCount = 0
    failCount = 0
    replyCount = 0
    currentMessage = None
    messageQueue = None
    jobQueue = None
    dataClass = None
    invokeController = None
    sendQueueName = None

    def __init__(self):
        raise Exception('Abstract class cannot be instantiated.')

    def run(self):
        pass

    def on_task(self, message):
        pass


class TaskThread(AbstractThread):
    def __init__(self, job_queue, data_class, invoke_controller, send_queue_name):
        Thread.__init__(self)
        self.jobQueue = job_queue
        self.dataClass = data_class
        self.invokeController = invoke_controller
        self.sendQueueName = send_queue_name
        self.daemon = True
        self.create_mq_connection_and_channel()
        logger.debug('TaskThread instance has been created : Name=\'%s\'' % self.name)
        self.start()

    def create_mq_connection_and_channel(self):
        self.messageQueue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.messageQueue.create_send_channel(self.sendQueueName, durable=True)

    def run(self):
        while self.exitFlag is False:
            if self.processedCount is 0:
                logger.info('%s starts consuming the internal queue : Queue=%s' % (self.__class__.__name__, str(self.jobQueue)))
            message = self.jobQueue.get(block=True)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('%s received a message from internal queue : Message=\'%s\'' % (self.__class__.__name__, message.replace('\r', '\\r').replace('\n', '\\n')))
            if message == 'stop thread':
                logger.debug('%s has been requested to stop.' % self.__class__.__name__)
                self.jobQueue.task_done()
                self.exitFlag = True
            else:
                self.on_task(message)
        logger.info('%s has been stopped.' % self.__class__.__name__)

    def on_task(self, message):
        data = None
        try:
            self.runFlag = True
            self.startTime = time.time()
            self.currentMessage = message
            data = self.dataClass(message)
            result = self.invokeController.run(data)
            if result and data.need_reply():
                while True:
                    try:
                        self.messageQueue.send(result.get_json_data())
                        self.replyCount += 1
                        logger.debug('Sent response to the outbound queue : Message=%s' % result.get_json_data())
                        break
                    except ConnectionClosed:
                        logger.warn('Queue send channel for message is closed. reconnecting... : Queue=%s' % self.sendQueueName)
                        self.create_mq_connection_and_channel()
                        time.sleep(1)
        except BaseException as e:
            error_logger.exception('Exception occurred during processing a message.')
            logger.error('Exception occurred during processing a message : Exception=\'%s\', Message=\'%s\'' % (e, message))
        finally:
            success = False
            if data:
                try:
                    op_code = data.get_op_code(throw_if_absence=False)
                    company = data.get_company_code(throw_if_absence=False)
                    channel = data.get_client_channel_id(throw_if_absence=False)
                    module = clazz = function = None
                    if op_code:
                        module = op_code.get('module')
                        clazz = op_code.get('class')
                        function = op_code.get('function')
                    success = result.is_success() if result else False
                    reply = data.need_reply() if result else False
                    op_data = data.get_op_data(throw_if_absence=False)
                    req_size = len(str(op_data)) if op_data else '-'
                    if success:
                        op_data = result.get_op_data(throw_if_absence=False) if result else '-'
                        res_size = len(str(op_data)) if op_data else 0
                    else:
                        res_size = '-'
                    access_logger.info('[TASK] %s %s "%s:%s:%s" %s %s %s %s %.3f' % (company, channel, module, clazz, function, success, reply, req_size, res_size, (time.time()-self.startTime)))
                except BaseException as ee:
                    access_logger.info('[TASK] - - "-:-:-" ? ? - - %.3f' % (time.time() - self.startTime))
                    error_logger.exception('Exception occurred during writing result of a task to accesslog.')
                    logger.warn('Exception occurred during writing result of a task to accesslog : Exception=\'%s\'' % ee)
            else:
                access_logger.info('[TASK] - - "-:-:-" %s False - - %.3f' % (success, (time.time() - self.startTime)))
            self.processedCount += 1
            if success:
                self.successCount += 1
            else:
                self.failCount += 1
            self.currentMessage = None
            self.startTime = 0
            self.runFlag = False
            self.jobQueue.task_done()


class MgmtThread(AbstractThread):
    def __init__(self, job_queue, data_class, invoke_controller, send_queue_name):
        Thread.__init__(self)
        self.jobQueue = job_queue
        self.dataClass = data_class
        self.invokeController = invoke_controller
        self.sendQueueName = send_queue_name
        self.daemon = True
        self.create_mq_connection_and_channel()
        logger.debug('MgmtThread instance has been created : Name=\'%s\'' % self.name)
        self.start()

    def create_mq_connection_and_channel(self):
        self.messageQueue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.messageQueue.create_send_channel(self.sendQueueName, durable=True)

    def run(self):
        while self.exitFlag is False:
            if self.processedCount is 0:
                logger.info('%s starts consuming the internal queue : Queue=%s' % (self.__class__.__name__, str(self.jobQueue)))
            message = self.jobQueue.get(block=True)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug('%s received a message from internal queue : Message=\'%s\'' % (self.__class__.__name__, message.replace('\r', '\\r').replace('\n', '\\n')))
            if message == 'stop thread':
                logger.debug('%s has been requested to stop.' % self.__class__.__name__)
                self.jobQueue.task_done()
                self.exitFlag = True
            else:
                self.on_task(message)
        logger.info('%s has been stopped.' % self.__class__.__name__)

    def on_task(self, message):
        data = None
        try:
            self.runFlag = True
            self.startTime = time.time()
            self.currentMessage = message
            data = self.dataClass(message)
            result = self.invokeController.run(data)
            if result and data.need_reply():
                while True:
                    try:
                        self.messageQueue.send(result.get_json_data())
                        self.replyCount += 1
                        logger.debug('Sent response to the outbound queue : Message=%s' % result.get_json_data())
                        break
                    except ConnectionClosed:
                        logger.warn('Queue send channel for management is closed. reconnecting... : Queue=%s' % self.sendQueueName)
                        self.create_mq_connection_and_channel()
                        time.sleep(1)
        except BaseException as e:
            error_logger.exception('Exception occurred during processing a message.')
            logger.error('Exception occurred during processing a message : Exception=\'%s\', Message=\'%s\'' % (e, message))
        finally:
            success = False
            if data:
                try:
                    action = data.get_op_action(throw_if_absence=False)
                    target = data.get_op_target(throw_if_absence=False)
                    detail = data.get_op_detail(throw_if_absence=False)
                    success = result.is_success() if result else False
                    reply = data.need_reply() if result else False
                    access_logger.info('[MGMT] - - "%s:%s:%s" %s %s - - %.3f' % (action, target, detail, success, reply, (time.time()-self.startTime)))
                except BaseException as ee:
                    access_logger.info('[MGMT] - - "-:-:-" ? ? - - %.3f' % (time.time() - self.startTime))
                    error_logger.exception('Exception occurred during writing result of a mgmt to accesslog.')
                    logger.warn('Exception occurred during writing result of a mgmt to accesslog : Exception=\'%s\'' % ee)
            else:
                access_logger.info('[MGMT] - - "-:-:-" %s False - - %.3f' % (success, (time.time() - self.startTime)))
            self.processedCount += 1
            if success:
                self.successCount += 1
            else:
                self.failCount += 1
            self.currentMessage = None
            self.startTime = 0
            self.runFlag = False
            self.jobQueue.task_done()