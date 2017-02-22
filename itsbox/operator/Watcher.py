#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import operator
import time
from threading import Thread

from pika.exceptions import ConnectionClosed

from itsbox.operator import Config
from itsbox.operator.Message import MgmtData
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')


class WatcherThread(Thread):
    exitFlag = False
    waitFlag = False
    workers = {}
    workerListLock = None
    interval = 0
    queue = None

    def __init__(self, workers, lock=None, interval=5):
        Thread.__init__(self, target=self.start_thread)
        self.workers = workers
        self.workerListLock = lock
        self.interval = interval
        self.name = 'WorkerWatcher'
        self.daemon = True
        logger.debug('Watcher instance has been created : CheckIntervalSec=%d' % interval)

    def create_mq_connection_and_channel(self):
        self.queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.queue.create_send_channel(Config.RABBITMQ_QNAME_MGMT_IN, durable=True)

    def start_thread(self):
        logger.debug('WorkerWatcher is starting...')
        self.create_mq_connection_and_channel()
        logger.debug('WorkerWatcher is monitoring the dead workers...')
        while self.exitFlag is False:
            time.sleep(self.interval)
            try:
                self.watcher_run()
            except BaseException as e:
                error_logger.exception('Exception occurred during watching running workers.')
                logger.error('Exception occurred during watching running workers : Exception=\'%s\'' % e)
        logger.debug('WorkerWatcher has been stopped.')

    def stop_thread(self):
        logger.debug('Watcher has been requested to stop.')
        self.exitFlag = True

    def watcher_run(self):
        enter_flag = True
        while self.waitFlag:
            if enter_flag:
                enter_flag = False
                logger.info('Watcher is pausing for a while.')
            time.sleep(1)
        if enter_flag is False:
            logger.info('Watcher resumes task.')
        self.check_workers()

    def check_workers(self):
        logger.debug('Watcher is checking dead workers.')
        if len(self.workers) == 0:
            logger.warn('No worker is alive.')
            return
        good_status = True
        sorted_workers = sorted(self.workers.items(), key=operator.itemgetter(0))
        for pid, worker in sorted_workers:
            try:
                worker_downed = False
                if worker.is_alive() is False:
                    logger.warn('Worker down has been detected : PID=%d, Worker=%s' % (pid, worker))
                    try:
                        if self.workerListLock:
                            self.workerListLock.acquire()
                        if self.workers.get(pid):
                            del self.workers[pid]
                    finally:
                        if self.workerListLock:
                            self.workerListLock.release()
                    worker_downed = True
                    good_status = False
            except BaseException as e:
                error_logger.exception('Exception occurred during checking a worker.')
                logger.error('Exception occurred during checking a worker : PID=%d, Exception=\'%s\'' % (pid, e))
            finally:
                if worker_downed:
                    send_msg = MgmtData()
                    send_msg.set_op_action('start')
                    send_msg.set_op_target('worker')
                    send_msg.set_op_detail('1')
                    send_msg.set_reply(False)
                    while self.queue and self.queue.connection.is_open:
                        try:
                            self.queue.send(send_msg.get_json_data())
                            logger.info('A worker has been requested to start.')
                            break
                        except ConnectionClosed:
                            logger.warn('Queue send channel for management is closed. reconnecting... : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_IN)
                            self.create_mq_connection_and_channel()
                            time.sleep(1)
        if good_status:
            logger.debug('All workers is alive : Workers=%s' % sorted_workers)
