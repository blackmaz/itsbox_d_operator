#!/usr/bin/python
#-*- coding: utf-8 -*-
import os
import sys
import threading
import time


def aaa(argument_list):
    print('%s.%s has been called with %d arguments' % (InfraClass.__name__, sys._getframe().f_code.co_name, len(argument_list)))
    time.sleep(5)
    return 'Return message from InfraSample.aaa() ~~'


class InfraClass:
    def __init__(self):
        pass

    @staticmethod
    def infra_static_function(argument_list):
        curr_time = time.time()
        print('[%d][%s] %s.%s has been called with %d arguments : Key=%f' % (os.getpid(), threading.currentThread(), InfraClass.__name__, sys._getframe().f_code.co_name, len(argument_list), curr_time))
        time.sleep(10)
        print('[%d][%s] %s.%s has been finished calling : Key=%f' % (os.getpid(), threading.currentThread(), InfraClass.__name__, sys._getframe().f_code.co_name, curr_time))
        return 'Return message from InfraClass.infra_static_function() ~~'

    def infra_function(self, argument_list):
        print('%s.%s has been called with %d arguments' % (self.__class__.__name__, sys._getframe().f_code.co_name, len(argument_list)))
        time.sleep(5)
        return 'Return message from InfraClass.infra_function() ~~'


if __name__ == '__main__':
    result = aaa()
    result = InfraClass.infra_static_function(['test'])
    result = InfraClass().infra_function(['tttt'])
