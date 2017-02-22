#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import re
from threading import Thread

from itsbox.operator import Config
from itsbox.operator.Message import MgmtData, TaskData
from itsbox.util import DynamicCall

logger = logging.getLogger('engine')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')


class TaskController:
    def __init__(self):
        logger.debug('TaskController instance has been created.')

    def run(self, data):
        if isinstance(data, TaskData) is False:
            raise TypeError('The argument of TaskController sould be type of TaskData.')
        to_return = data.clone()
        try:
            if data.is_inbound_direction() is False:
                logger.warn('Outbound message is queued in inbound queue. It will be transferring to outbound queue.')
                return data
            elif data.is_operator_location() is False:
                logger.warn('The message is not for operator. It will be ignored.')
                return None

            op_code = data.get_op_code()
            op_data = data.get_op_data()
            module_name = Config.RULE_MODULE_BASE + '.' + op_code.get('module')
            class_name = op_code.get('class')
            function_name = op_code.get('function')

            logger.info('TaskController is processing a task : OpCode=%s, OpData=%s' % (op_code, op_data))
            if class_name:
                result = DynamicCall.call_class_static_function(module_name, class_name, function_name, op_data)
            else:
                result = DynamicCall.call_module_static_function(module_name, function_name, op_data)
            logger.info('TaskController was finished to process a task : OpCode=%s, OpData=%s, Result=\'%s\'' % (op_code, op_data, result))

            to_return.set_success(True)
            to_return.set_message(str(result) if result else '')
        except KeyError as ke:
            error_logger.exception('Cannot find %s key.' % ke)
            logger.error('KeyError occurred in TaskController : NotFoundKey=%s' % ke)
            to_return.set_success(False)
            to_return.set_message('Cannot find "%s" value from input data' % ke)
        except Exception as e:
            error_logger.exception('Exception occurred in TaskController.')
            logger.error('Exception occurred in TaskController : Exception=\'%s\'' % e)
            to_return.set_success(False)
            to_return.set_message(str(e))
        finally:
            to_return.set_time()
            to_return.set_direction(inbound=False)
            to_return.encode()
        return to_return


class MgmtController:
    manager = None

    def __init__(self, manager):
        self.manager = manager
        logger.debug('MgmtController instance has been created.')

    def run(self, data):
        if isinstance(data, MgmtData) is False:
            raise TypeError('The argument of MgmtController sould be type of MgmtData.')
        to_return = data.clone()
        try:
            if data.is_inbound_direction() is False:
                logger.warn('Outbound management message is queued in inbound queue. It will be transferring to outbound queue.')
                return data
            elif data.is_operator_location() is False:
                logger.warn('The management message is not for operator. It will be ignored.')
                return None

            op_action = data.get_op_action()
            op_target = data.get_op_target()
            op_detail = data.get_op_detail(throw_if_absence=False)
            logger.info('MgmtController is processing a task : Action=%s, Target=%s, Detail=\'%s\'' % (op_action, op_target, op_detail))
            result = self.process(op_action, op_target, op_detail)
            logger.info('MgmtController was finished to process a task : Action=%s, Target=%s, Detail=\'%s\', Result=\'%s\'' % (op_action, op_target, op_detail, result))
            to_return.set_success(True)
            if result:
                to_return.set_message(result)
        except KeyError as ke:
            error_logger.exception('Cannot find %s key.' % ke)
            logger.error('KeyError occurred in MgmtController : NotFoundKey=%s' % ke)
            to_return.set_success(False)
            to_return.set_message('Cannot find "%s" value from input data' % ke)
        except Exception as e:
            error_logger.exception('Exception occurred in MgmtController.')
            logger.error('Exception occurred in MgmtController : Exception=\'%s\'' % e)
            to_return.set_success(False)
            to_return.set_message(str(e))
        finally:
            to_return.set_time()
            to_return.set_direction(inbound=False)
            to_return.encode()
        return to_return

    def process(self, action, target, detail=None):
        if target is None or target == '':
            raise SyntaxError('Need a target')

        if action == 'start':
            if target == 'worker':
                if detail is None or detail == '':
                    raise SyntaxError('Need worker count to start')
                elif detail == 'all':
                    self.manager.start_workers()
                    return 'Successfully started all workers(process=default[%s],thread=default[%s])' % (Config.WORKER_COUNT, Config.THREAD_COUNT)
                else:
                    p = re.compile('^(?P<prc>\d+)(\((?P<thr>\d+)\))?$')
                    if p.match(detail):
                        m = p.search(detail)
                        prc_count = m.group('prc')
                        thr_count = m.group('thr')
                        if thr_count:
                            self.manager.start_workers(int(prc_count), int(thr_count))
                            return 'Successfully started workers(process=%s,thread=%s)' % (prc_count, thr_count)
                        else:
                            self.manager.start_workers(int(prc_count))
                            return 'Successfully started workers(process=%s,thread=default[%s])' % (prc_count, Config.THREAD_COUNT)
                    else:
                        raise SyntaxError('Unknown worker(thread) count %s : ' % detail)
            elif target == 'watcher':
                self.manager.start_watcher()
                return 'Successfully started the watcher.'
            elif target == 'management':
                self.manager.start_management()
                return 'Successfully started the management.'
            else:
                raise SyntaxError('Unknown target')

        elif action == 'stop':
            if target == 'worker':
                if detail is None or detail == '':
                    raise SyntaxError('Need worker count or pid to stop')
                elif detail == 'all':
                    self.manager.stop_workers()
                    return 'Successfully stopped the all workers.'
                else:
                    if len(detail) > 4 and detail[0:4] == 'pid=':
                        self.manager.stop_workers(worker_pid=int(detail[4:]))
                    elif len(detail) > 6 and detail[0:6] == 'count=':
                        self.manager.stop_workers(worker_count=int(detail[6:]))
                    else:
                        raise SyntaxError('Unknown worker count or pid')
                    return 'Successfully stopped the workers(%s)' % detail
            elif target == 'watcher':
                self.manager.stop_watcher()
                return 'Successfully stopped the watcher.'
            elif target == 'management':
                self.manager.stop_management()
                return 'Successfully stopped the management.'
            elif target == 'all':
                logger.debug('Stopping the operator will be done asynchronously.')
                Thread(target=lambda: self.manager.stop()).start()
                return 'Stopping the operator will be done asynchronously.'
            else:
                raise SyntaxError('Unknown target')

        elif action == 'info':
            if target == 'worker':
                if detail is None or detail == '':
                    raise SyntaxError('Need worker pid to get info')
                elif detail == 'all':
                    workers_info, total_workers_info = self.manager.get_worker_info()
                    return {'workers': workers_info, 'total': total_workers_info}
                else:
                    if len(detail) > 4 and detail[0:4] == 'pid=':
                        workers_info, total_workers_info = self.manager.get_worker_info(worker_pid=int(detail[4:]))
                        return {'workers': workers_info, 'total': total_workers_info}
                    else:
                        raise SyntaxError('Unknown worker pid')
            else:
                raise SyntaxError('Unknown target')

        else:
            raise SyntaxError('Unknown command')
