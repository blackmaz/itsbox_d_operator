#!/usr/bin/python
#-*- coding: utf-8 -*-
import time

import logging

from itsbox.operator.infra.AWS import *

error_logger = logging.getLogger('error')


def getSizeList(op_data):
    try:
        aws = AWS(access_key=op_data['access'], secret_key=op_data['secret'], region_name=op_data['region'], secure=False)
        aws.network.test()
        aws.security.test()
        aws.node.test()
        aws.loadBalance.test()
        time.sleep(5)
        return aws.list_sizes()
    except Exception as e:
        error_logger.exception('Exception occurred during calling a rule.')
        raise e
