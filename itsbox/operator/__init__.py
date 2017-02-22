#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging.handlers
import os
import sys

from itsbox.operator import Config

reload(sys)
sys.setdefaultencoding('utf-8')

if not os.path.exists(Config.LOG_FILE_DIR):
    os.makedirs(Config.LOG_FILE_DIR)

engine_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] [%(process)d] [%(threadName)s] [%(funcName)s(%(filename)s:%(lineno)s)] %(message)s')
access_formatter = logging.Formatter('[%(asctime)s] %(message)s')


consoleHandler = logging.StreamHandler()
consoleHandler.setLevel(logging.CRITICAL)
logging.getLogger().addHandler(consoleHandler)


log_file_prefix = os.path.join(Config.LOG_FILE_DIR, Config.LOG_FILE_PREFIX)
log_file_suffix = '_all.log' if Config.LOG_FILE_ALLINONE else '_engine.log'
if Config.LOG_FILE_ROTATION:
    engine_fileHandler = logging.handlers.RotatingFileHandler(log_file_prefix+log_file_suffix, maxBytes=Config.LOG_FILE_MAX_BYTES, backupCount=Config.LOG_FILE_MAX_COUNT)
else:
    engine_fileHandler = logging.FileHandler(log_file_prefix+log_file_suffix)
engine_fileHandler.setFormatter(engine_formatter)
engine_fileHandler.setLevel(Config.LOG_LEVEL)
logging.getLogger('engine').addHandler(engine_fileHandler)
logging.getLogger('util').addHandler(engine_fileHandler)


log_file_suffix = '_all.log' if Config.LOG_FILE_ALLINONE else '_access.log'
if Config.LOG_FILE_ROTATION:
    access_fileHandler = logging.handlers.RotatingFileHandler(log_file_prefix+log_file_suffix, maxBytes=Config.LOG_FILE_MAX_BYTES, backupCount=Config.LOG_FILE_MAX_COUNT)
else:
    access_fileHandler = logging.FileHandler(log_file_prefix+log_file_suffix)
access_fileHandler.setFormatter(access_formatter)
access_fileHandler.setLevel(logging.DEBUG)
logging.getLogger('access').addHandler(access_fileHandler)


log_file_suffix = '_all.log' if Config.LOG_FILE_ALLINONE else '_error.log'
if Config.LOG_FILE_ROTATION:
    error_fileHandler = logging.handlers.RotatingFileHandler(log_file_prefix+log_file_suffix, maxBytes=Config.LOG_FILE_MAX_BYTES, backupCount=Config.LOG_FILE_MAX_COUNT)
else:
    error_fileHandler = logging.FileHandler(log_file_prefix+log_file_suffix)
error_fileHandler.setFormatter(engine_formatter)
logging.getLogger('error').addHandler(error_fileHandler)

