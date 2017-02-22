#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging

from itsbox.operator import Config

logger = logging.getLogger('util')
logger.setLevel(Config.LOG_LEVEL)


def call_module_static_function(module_name, function_name, argument_list={}):
    if module_name is None or function_name is None:
        raise Exception('Module and function name cannot be None.')
    if type(module_name) is unicode:
        module_name = str(module_name)
    idx = module_name.rindex('.')
    pkg = module_name[:idx]
    m = module_name[idx+1:]
    mod = __import__(pkg, fromlist=[m])
    cls = getattr(mod, m)
    func = getattr(cls, function_name)
    logger.debug('Calling module static function : module=%s, function=%s, arguments=%s' % (module_name, function_name, argument_list))
    return func(argument_list)


def call_class_static_function(module_name, class_name, function_name, argument_list={}):
    if module_name is None or class_name is None or function_name is None:
        raise Exception('Module, class and function name cannot be None.')
    mod = __import__(module_name, fromlist=[class_name])
    cls = getattr(mod, class_name)
    func = getattr(cls, function_name)
    logger.debug('Calling class static function : module=%s, class=%s, function=%s, arguments=%s' % (module_name, class_name, function_name, argument_list))
    return func(argument_list)


def call_class_instance_function(module_name, class_name, function_name, argument_list={}):
    if module_name is None or class_name is None or function_name is None:
        raise Exception('Module, class and function name cannot be None.')
    mod = __import__(module_name, fromlist=[class_name])
    cls = getattr(mod, class_name)
    func = getattr(cls(), function_name)
    logger.debug('Calling class function : module=%s, class=%s, function=%s, arguments=%s' % (module_name, class_name, function_name, argument_list))
    return func(argument_list)
