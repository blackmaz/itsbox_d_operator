#!/usr/bin/python
#-*- coding: utf-8 -*-
import sys
import traceback

from itsbox.operator import Config
from itsbox.operator.Manager import ManagerProcess

if __name__ == '__main__':
    if len(sys.argv) == 1:
        manager = ManagerProcess(worker_count=Config.WORKER_COUNT)
        try:
            pid = manager.lock()
            if pid is None:
                try:
                    manager.start()
                except BaseException as e:
                    print('Failed to start operator manager : Exception="%s"' % e)
                    traceback.print_exc()
                finally:
                    manager.release()
            else:
                print('Another manager is running. Please stop the booted manager first : PID=%d' % pid)
        except BaseException as e:
            print('Exception occurred during starting up the manager : Exception="%s"' % e)
    else:
        print('Unknown argument or Too many arguments')
        print('USAGE : python %s' % sys.argv[0])

