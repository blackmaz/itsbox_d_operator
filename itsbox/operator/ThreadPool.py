#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import time

from queue import Queue

from itsbox.operator import Config
from itsbox.operator.Controller import TaskController, MgmtController
from itsbox.operator.Message import TaskData, MgmtData
from itsbox.operator.Thread import TaskThread
from itsbox.operator.Thread import MgmtThread

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)


class AbstractThreadPool:
    jobQueue = None
    invokeController = None
    threads = {}

    def __init__(self):
        raise Exception('Abstract class cannot be instantiated.')

    def add_task(self, message):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Transferred a task to internal queue : Message=\'%s\'' % message.replace('\r', '\\r').replace('\n', '\\n'))
        self.jobQueue.put(message)

    def stop_task(self, wait=False):
        logger.debug('%s is requesting threads to stop : Wait=%s' % (self.__class__.__name__, wait))
        for _ in range(len(self.threads)):
            self.add_task('stop thread')
        if wait:
            logger.debug('Waiting until all threads stop.')
            for tid in self.threads.keys():
                t = self.threads[tid]
                logger.debug('Waiting until the thread terminates : TID=%d, Name=\'%s\'' % (tid, t.getName()))
                t.join()
                logger.debug('The thread has terminated : TID=%d, Name=\'%s\'' % (tid, t.getName()))
            logger.debug('All threads have been stopped.')

    def get_active_tasks(self):
        logger.debug('Requested to get active threads in progress.')
        active_threads = []
        for tid in self.threads.keys():
            if self.threads[tid].runFlag:
                active = { 'tid':tid,
                           'thread':self.threads[tid].name,
                           'start':self.threads[tid].startTime,
                           'duration':time.time() - self.threads[tid].startTime,
                           'message':self.threads[tid].currentMessage }
                active_threads.append(active)
        return active_threads

    def get_processed_count(self):
        logger.debug('Requested to get count of processed tasks.')
        process = success = fail = reply = 0
        for tid in self.threads.keys():
            process += self.threads[tid].processedCount
            success += self.threads[tid].successCount
            fail += self.threads[tid].failCount
            reply += self.threads[tid].replyCount
        return process, success, fail, reply


class TaskThreadPool(AbstractThreadPool):
    def __init__(self, thread_count):
        self.jobQueue = Queue()
        self.invokeController = TaskController()
        for _ in range(thread_count):
            thr = TaskThread(self.jobQueue, TaskData, self.invokeController, Config.RABBITMQ_QNAME_MSG_OUT)
            self.threads[thr.ident] = thr
        logger.debug('TaskThreadPool instance has been created : ThreadCount=%d' % thread_count)


class MgmtThreadPool(AbstractThreadPool):
    def __init__(self, manager, thread_count):
        self.jobQueue = Queue()
        self.invokeController = MgmtController(manager)
        for _ in range(thread_count):
            thr = MgmtThread(self.jobQueue, MgmtData, self.invokeController, Config.RABBITMQ_QNAME_MGMT_OUT)
            self.threads[thr.ident] = thr
        logger.debug('MgmtThreadPool instance has been created : ThreadCount=%d' % thread_count)
