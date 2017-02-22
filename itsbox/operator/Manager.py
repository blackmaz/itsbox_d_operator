#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import operator
import os
import signal
import tempfile
import threading
import time
from threading import Thread, Lock

import psutil
from pika.exceptions import ConnectionClosed

from itsbox.operator import Config
from itsbox.operator.Controller import MgmtController
from itsbox.operator.Management import WebsocketMgmtServer
from itsbox.operator.Message import MgmtData
from itsbox.operator.ThreadPool import MgmtThreadPool
from itsbox.operator.Watcher import WatcherThread
from itsbox.operator.Worker import WorkerProcess
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')


class ManagerProcess:
    exitFlag = False
    signalReceived = False
    pid = 0
    wsMgmtServer = None
    watcher = None
    workerCount = 0
    receivedCount = 0
    threadPool = None
    mgmtController = None
    queue = None
    workers = {}
    workerListLock = Lock()
    endEvent = threading.Event()

    def __init__(self, worker_count=10):
        self.workerCount = worker_count
        logger.debug('Manager instance has been created : WorkerCount=%d' % worker_count)
        signal.signal(signal.SIGINT, self.destroy)
        signal.signal(signal.SIGTERM, self.destroy)
        signal.signal(signal.SIGABRT, self.destroy)
        logger.debug('Signal handler for manager has been registered.')

    def create_mq_connection_and_channel(self):
        self.queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
        self.queue.create_send_channel(Config.RABBITMQ_QNAME_MGMT_OUT, durable=True)
        self.queue.create_receive_channel(Config.RABBITMQ_QNAME_MGMT_IN, durable=True)

    def on_message(self, channel, method, properties, message):
        self.receivedCount += 1
        message = message.decode('utf-8') if type(message) is bytes else message
        message = message.strip()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Manager received a message from queue : Message=\'%s\'' % message.replace('\r', '\\r').replace('\n', '\\n'))
        self.threadPool.add_task(message)

    def start_workers(self, worker_count=None, thread_count=None):
        if worker_count is None:
            if len(self.workers) > 0:
                raise SyntaxError('Worker process is already running. Please input workers count.')
            else:
                worker_count = self.workerCount
        if worker_count <= 0 or (thread_count is not None and thread_count <= 0):
            raise SyntaxError('Process and Thread count cannot be 0 or less : Process=%s, Thread=%s' % (worker_count, thread_count))
        elif worker_count + len(self.workers) > Config.MAX_WORKER_PER_NODE or thread_count > Config.MAX_THREAD_PER_WORKER:
            raise SyntaxError('Process and Thread count cannot be over max config : MaxProcess=%s, MaxThread=%s' % (Config.MAX_WORKER_PER_NODE, Config.MAX_THREAD_PER_WORKER))
        for i in range(worker_count):
            try:
                if thread_count:
                    worker = WorkerProcess(thread_count)
                else:
                    worker = WorkerProcess(Config.THREAD_COUNT)
                worker.start()
                if worker.is_alive() and not worker.stoppingFlag:
                    try:
                        self.workerListLock.acquire()
                        self.workers[worker.pid] = worker
                        self.receive_from_pipe(worker.parentPipe, worker.pid)
                        worker.readyFlag = True
                        logger.debug('Starting the worker was completed : PID=%d' % worker.pid)
                        print('Started a worker process : PID=%d' % worker.pid)
                    finally:
                        self.workerListLock.release()
            except BaseException as e:
                error_logger.exception('Exception occurred during starting a worker.')
                logger.error('Exception occurred during starting a worker : Exception=\'%s\'' % e)

    def stop_workers(self, worker_count=None, worker_pid=None):
        if worker_count is not None and worker_pid is not None:
            raise SyntaxError('Stopping worker cannot be operated with both count and pid.')
        try:
            if self.watcher and self.watcher.is_alive():
                logger.info('Requested watcher to pause monitoring workers for a while.')
                self.watcher.waitFlag = True
            if worker_pid:
                self.stop_worker(worker_pid)
            else:
                logger.info('Manager is stopping all workers.')
                current_count = len(self.workers)
                if worker_count is None or worker_count == 0:
                    worker_count = current_count
                if current_count < worker_count:
                    raise Exception('Stop count is greater than current worker count(CurrentWorkerCount=%d)' % current_count)
                else:
                    stop_count = worker_count
                if stop_count <= 0:
                    logger.info('There is no worker to stop.')
                    return
                count = 0
                stop_threads = []
                for pid, worker in sorted(self.workers.items(), key=operator.itemgetter(0)):
                    t = Thread(target=self.stop_worker, args=(pid,))
                    t.start()
                    stop_threads.append(t)
                    count += 1
                    if count is stop_count:
                        break
                for t in stop_threads:
                    t.join()
        finally:
            if self.watcher and self.watcher.is_alive():
                logger.info('Requested watcher to resume monitoring workers.')
                self.watcher.waitFlag = False

    def stop_worker(self, pid):
        if self.workers.get(pid) is None:
            logger.warn('The worker process is not running : PID=%s' % pid)
            return
        try:
            logger.info('Manager is stopping the worker : PID=%s' % pid)
            worker = self.workers[pid]
            if not worker.is_alive():
                logger.debug('The worker was already down : PID=%s' % pid)
            elif not worker.readyFlag:
                logger.debug('The worker is starting and cannot be stopped : PID=%s' % pid)
            elif worker.stoppingFlag:
                logger.debug('The worker is already stopping : PID=%s' % pid)
            else:
                worker.stoppingFlag = True
                request_dict = {'time': int(time.time()), 'command': 'stop_worker', 'option': ''}
                response_dict = self.send_to_pipe_and_receive(worker.parentPipe, request_dict, pid)
                if response_dict:
                    logger.debug('Successfully stopped the worker : PID=%s' % pid)
                    try:
                        self.workerListLock.acquire()
                        del self.workers[pid]
                        print('Stopped the worker successfully : PID=%d' % pid)
                    finally:
                        self.workerListLock.release()
                else:
                    logger.error('Response from worker pipe is None.')
        except BaseException as e:
            error_logger.exception('Exception occurred during stopping a worker.')
            logger.error('Exception occurred during stopping a worker : PID=%s, Exception=\'%s\'' % (pid, e))

    def get_worker_info(self, worker_pid=None):
        if worker_pid is not None and self.workers.get(worker_pid) is None:
            raise SyntaxError('The worker process is not running : PID=%s' % worker_pid)
        workers_info = []
        for pid, worker in sorted(self.workers.items(), key=operator.itemgetter(0)):
            try:
                if worker_pid is None or worker_pid == pid:
                    if worker.is_alive() and worker.readyFlag and not worker.stoppingFlag:
                        request_dict = { 'time':int(time.time()), 'command':'get_worker_info' }
                        worker_info = self.send_to_pipe_and_receive(worker.parentPipe, request_dict, pid, timeout=Config.MANAGER_REQUEST_TIMEOUT_PER_WORKER)
                        if worker_info:
                            if worker_info.get('message') == 'Timeout occurred':
                                logger.warn('Timeout occurred while receiving from worker pipe. Please wait until worker finished : Timeout=%d' % Config.MANAGER_REQUEST_TIMEOUT_PER_WORKER)
                            workers_info.append(worker_info)
            except BaseException as e:
                error_logger.exception('Exception occurred during request get_worker_info to worker.')
                logger.error('Exception occurred during request get_worker_info to worker : PID=%d, Exception=\'%s\'' % (pid, e))
        total_workers_info = None
        if workers_info and len(workers_info) > 0  and worker_pid is None:
            w_full = w_active = w_idle = t_total = t_active = t_idle = c_receive = c_process = c_success = c_fail = c_reply = queued = 0
            for each_info in workers_info:
                if each_info.get('status'):
                    w_full += 1 if each_info['status'] == 'Full' else 0
                    w_active += 1 if each_info['status'] == 'Active' else 0
                    w_idle += 1 if each_info['status'] == 'Idle' else 0
                if each_info.get('thread'):
                    t_total += each_info['thread']['total']
                    t_active += each_info['thread']['active']
                    t_idle += each_info['thread']['idle']
                if each_info.get('count'):
                    c_receive += each_info['count']['receive']
                    c_process += each_info['count']['process']
                    c_success += each_info['count']['success']
                    c_fail += each_info['count']['fail']
                    c_reply += each_info['count']['reply']
                if each_info.get('queued'):
                    queued += each_info['queued']
            total_workers_info = { 'worker':{'total':len(workers_info), 'full':w_full, 'active':w_active, 'idle':w_idle},
                                   'thread':{'total':t_total, 'active':t_active, 'idle':t_idle},
                                   'count':{'receive':c_receive, 'process':c_process, 'success':c_success, 'fail':c_fail, 'reply':c_reply},
                                   'status':'Unknown',
                                   'queued':queued }
            if total_workers_info['thread']['idle'] == 0:
                total_workers_info['status'] = 'Full'
            elif total_workers_info['thread']['active'] > 0:
                total_workers_info['status'] = 'Active'
            else:
                total_workers_info['status'] = 'Idle'
        else:
            total_workers_info = { 'worker':{'total':0, 'full':0, 'active':0, 'idle':0},
                                   'thread':{'total':0, 'active':0, 'idle':0},
                                   'count':{'receive':0, 'process':0, 'success':0, 'fail':0, 'reply':0},
                                   'status':'Down',
                                   'queued':0 }
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('Total worker info : \'%s\'' % total_workers_info)
        return workers_info, total_workers_info

    def receive_from_pipe(self, pipe, pid=None, timeout=None):
        response_dict = {}
        logger.debug('Waiting until the process responds : PID=%s, Timeout=%s' % (pid, timeout))
        if pipe.poll(timeout):
            response_dict = pipe.recv()
            logger.debug('Received data from process pipe : PID=%s, Data=%s' % (pid, str(response_dict)))
        else:
            logger.debug('Timeout occurred while waiting for the process response : PID=%s, Timeout=%s' % (pid, timeout))
            response_dict['pid'] = pid
            response_dict['message'] = 'Timeout occurred'
        return response_dict

    def send_to_pipe_and_receive(self, pipe, request_dict, pid=None, timeout=None):
        response_dict = {}
        hash_value = hash(str(request_dict))
        request_dict['hash'] = hash_value
        pipe.send(request_dict)
        logger.debug('Sent data to process pipe. Waiting until the process responds : PID=%s, Data=%s, Timeout=%s' % (pid, str(request_dict), timeout))
        if pipe.poll(timeout):
            response_dict = pipe.recv()
            logger.debug('Received data from process pipe : PID=%s, Data=%s' % (pid, str(response_dict)))
            if response_dict is None or response_dict.get('hash') != hash_value:
                logger.critical('Wrong hash value in response data from process pipe : PID=%s, SendHash=%s, ReceiveHash=%s' % (pid, hash_value, response_dict.get('hash')))
                response_dict['pid'] = pid
                response_dict['message'] = 'Wrong hash'
            else:
                del response_dict['hash']
        else:
            logger.debug('Timeout occurred while waiting for the process response : PID=%s, Timeout=%s' % (pid, timeout))
            response_dict['pid'] = pid
            response_dict['message'] = 'Timeout occurred'
        return response_dict

    def start_watcher(self):
        if self.watcher is None:
            logger.debug('Manager is starting the watcher.')
            self.watcher = WatcherThread(self.workers, lock=self.workerListLock, interval=Config.WORKER_WATCHER_INTERVAL)
            self.watcher.start()
            logger.debug('Starting the watcher was completed.')
        else:
            logger.warn('Watcher is already running : TID=%d' % self.watcher.ident)
            raise Exception('Watcher is already running.')

    def stop_watcher(self):
        if self.watcher:
            if self.watcher.is_alive():
                logger.debug('Manager is stopping the watcher.')
                self.watcher.stop_thread()
                self.watcher = None
                logger.info('Successfully stopped the watcher.')
            else:
                logger.warn('Watcher is not alive.')
                raise Exception('Watcher is not alive.')
        else:
            logger.warn('Watcher is not running.')
            raise Exception('Watcher is not running.')

    def start_management(self):
        if self.wsMgmtServer is None:
            logger.debug('Manager is starting the management.')
            mgmt = WebsocketMgmtServer()
            mgmt.start()
            if mgmt.is_alive() and not mgmt.stoppingFlag:
                self.wsMgmtServer = mgmt
                self.receive_from_pipe(mgmt.parentPipe, mgmt.pid)
                mgmt.readyFlag = True
                logger.info('Starting the management was completed : PID=%d' % mgmt.pid)
                print('Started the management process : PID=%d' % mgmt.pid)
        else:
            logger.warn('The management is already running : TID=%d' % self.watcher.ident)
            raise Exception('The management is already running.')

    def stop_management(self):
        if self.wsMgmtServer is None:
            logger.warn('The management is not running.')
            raise Exception('The management is not running.')
        try:
            logger.info('Manager is stopping the management : PID=%s' % self.wsMgmtServer.pid)
            if not self.wsMgmtServer.is_alive():
                logger.debug('The management was already down : PID=%s' % self.wsMgmtServer.pid)
            elif not self.wsMgmtServer.readyFlag:
                logger.debug('The management is starting and cannot be stopped : PID=%s' % self.wsMgmtServer.pid)
            elif self.wsMgmtServer.stoppingFlag:
                logger.debug('The management is already stopping : PID=%s' % self.wsMgmtServer.pid)
            else:
                self.wsMgmtServer.stoppingFlag = True
                request_dict = {'time': int(time.time()), 'command': 'stop_management', 'option': ''}
                response_dict = self.send_to_pipe_and_receive(self.wsMgmtServer.parentPipe, request_dict, self.wsMgmtServer.pid)
                if response_dict:
                    logger.info('Successfully stopped the management : PID=%s' % self.wsMgmtServer)
                    print('Stopped the management successfully : PID=%d' % self.wsMgmtServer.pid)
                    self.wsMgmtServer = None
                else:
                    logger.error('Response from management pipe is None.')
        except BaseException as e:
            error_logger.exception('Exception occurred during stopping a management.')
            logger.error('Exception occurred during stopping a management : PID=%s, Exception=\'%s\'' % (self.wsMgmtServer, e))

    def start(self):
        printConfigurations()
        self.pid = os.getpid()
        logger.info('Manager is starting... : PID=%d' % self.pid)
        self.start_workers(thread_count=Config.THREAD_COUNT)
        self.start_watcher()
        self.threadPool = MgmtThreadPool(self, Config.THREAD_COUNT)
        self.create_mq_connection_and_channel()
        self.queue.purge(Config.RABBITMQ_QNAME_MGMT_IN)
        if Config.WEBSOCKET_MGMT_SERVER_BOOT:
            self.start_management()
        print('Hello! Ready to service...')
        while self.exitFlag is False:
            logger.info('Manager starts consuming the queue : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_IN)
            try:
                self.queue.start_receive(self.on_message, no_ack=True)
            except ConnectionClosed:
                logger.warn('Queue receive channel for management is closed. reconnecting... : Queue=%s' % Config.RABBITMQ_QNAME_MGMT_IN)
                self.create_mq_connection_and_channel()
            except BaseException as e:
                error_logger.exception('Exception occurred during consuming the queue.')
                logger.error('Exception occurred during consuming the queue : Queue=%s, Exception=%s' % (Config.RABBITMQ_QNAME_MGMT_IN, e))
            time.sleep(1)
        if not self.endEvent.isSet():
            logger.debug('Waiting until stop process finishes.')
            try:
                self.endEvent.wait()
            except KeyboardInterrupt:
                pass
        remain_task_count = self.threadPool.jobQueue.qsize()
        if remain_task_count > 0:
            logger.warn('Tasks remain in the internal queue. It will be lost : RemainTaskCount=%d' % remain_task_count)
        logger.info('Manager has been stopped.')
        print('Finished to service. Bye~')

    def stop(self):
        logger.info('Manager has been requested to stop.')
        if self.wsMgmtServer:
            try:
                self.stop_management()
            except BaseException:
                error_logger.exception('Exception occurred during stopping the management.')
        try:
            self.stop_watcher()
        except BaseException:
            error_logger.exception('Exception occurred during stopping the watcher.')
        try:
            self.stop_workers()
        except BaseException:
            error_logger.exception('Exception occurred during stopping the workers.')
        self.exitFlag = True
        if self.queue:
            try:
                self.queue.stop_receive()
            except BaseException:
                error_logger.exception('Exception occurred during stopping to receive queue.')
        if self.threadPool:
            try:
                self.threadPool.stop_task(wait=True)
            except BaseException:
                error_logger.exception('Exception occurred during stopping threads for management.')
        self.endEvent.set()
        logger.info('Manager was successfully stopped.')

    def destroy(self, signum, frame):
        if self.pid != 0 and self.pid == os.getpid():
            if self.signalReceived is False:
                self.signalReceived = True
                logger.info('Manager signal handler received signal : Signal=%d' % signum)
                print('Signal recevied. Operator will be gracefully stopped : Signal=%d' % signum)
                self.stop()

    def lock(self):
        lock_filename = os.path.join(tempfile.gettempdir(), 'OpManager.pid')
        f = None
        if os.path.isfile(lock_filename) is True:
            logger.debug('Lock file found : File=%s' % lock_filename)
            try:
                f = open(lock_filename, 'r')
                pid = f.read()
                if pid.strip():
                    logger.debug('Read lock file : Data=%s' % pid)
                    process = psutil.Process(int(pid))
                    if process.name()[0:6] == 'python' and process.cmdline():
                        valid_args = [arg for i,arg in enumerate(process.cmdline()) if arg[0:1] != '-' and i > 0]
                        if len(valid_args) > 0 and len(valid_args[0]) >= 26 and valid_args[0][-35:] == 'itsbox/operator/launcher/Startup.py':
                            return int(pid)
                    else:
                        logger.debug('Lock file is invalid.')
                        f.close()
                        self.release()
            except psutil.NoSuchProcess:
                logger.debug('No manager process is running.')
            except BaseException as e:
                error_logger.exception('Failed to read lock.')
                raise Exception('Failed to read lock : Exception=\'%s\'' % e)
            finally:
                if f:
                    f.close()
        f = None
        try:
            f = open(lock_filename, 'w+')
            f.write(str(os.getpid()))
            return None
        except BaseException as e:
            error_logger.exception('Failed to write lock.')
            raise Exception('Failed to write lock : Exception=\'%s\'' % e)
        finally:
            if f:
                f.flush()
                f.close()
                logger.debug('Lock file has been created : File=%s' % lock_filename)

    def release(self):
        lock_filename = os.path.join(tempfile.gettempdir(), 'OpManager.pid')
        try:
            if os.path.isfile(lock_filename) is True:
                os.remove(lock_filename)
        except BaseException as e:
            error_logger.exception('Failed to release lock.')
            logger.warn('Failed to release lock : Exception=\'%s\'' % e)


def printConfigurations():
    logger.info('='*50)
    logger.info(' - Logging')
    logger.info('   . Level : %s' % str(Config.LOG_LEVEL))
    logger.info('   . Log file directory : %s' % os.path.abspath(Config.LOG_FILE_DIR))
    logger.info('   . Log file prefix : %s' % Config.LOG_FILE_PREFIX)
    logger.info('   . Log file Rotation : %s' % Config.LOG_FILE_ROTATION)
    logger.info('   . Maximum size of log file : %d' % Config.LOG_FILE_MAX_BYTES)
    logger.info('   . Maximum count of log file : %d' % Config.LOG_FILE_MAX_COUNT)
    logger.info('   . All logs in one file : %s' % Config.LOG_FILE_ALLINONE)
    logger.info('-'*50)
    logger.info(' - MessageQueue')
    logger.info('   . Type : %s' % 'RabbitMQ')
    logger.info('   . IP : %s' % Config.RABBITMQ_IP)
    logger.info('   . Port : %s' % Config.RABBITMQ_PORT)
    logger.info('   . Vhost : %s' % Config.RABBITMQ_VHOST)
    logger.info('   . User : %s' % Config.RABBITMQ_USER)
    logger.info('   . Queue name for Management : %s / %s' % (Config.RABBITMQ_QNAME_MGMT_IN, Config.RABBITMQ_QNAME_MGMT_OUT))
    logger.info('   . Queue name for Message : %s / %s' % (Config.RABBITMQ_QNAME_MSG_IN, Config.RABBITMQ_QNAME_MSG_OUT))
    logger.info('-'*50)
    logger.info(' - Worker')
    logger.info('   . Maximum number of process and thread : %d processes / %d threads' % (Config.MAX_WORKER_PER_NODE, Config.MAX_THREAD_PER_WORKER))
    logger.info('   . Process count : %d' % Config.WORKER_COUNT)
    logger.info('   . Thread count : %d' % Config.THREAD_COUNT)
    logger.info('   . Watcher monitoring interval : %d sec' % Config.WORKER_WATCHER_INTERVAL)
    logger.info('   . Monitoring request timeout : %d sec' % Config.MANAGER_REQUEST_TIMEOUT_PER_WORKER)
    logger.info('-'*50)
    logger.info(' - ManagementServer')
    logger.info('   . Server booting : %s' % Config.WEBSOCKET_MGMT_SERVER_BOOT)
    logger.info('   . Server port : %d' % Config.WEBSOCKET_MGMT_SERVER_PORT)
    logger.info('-'*50)
    logger.info(' - Rule')
    logger.info('   . Rule module base : %s' % Config.RULE_MODULE_BASE)
    logger.info('='*50)
