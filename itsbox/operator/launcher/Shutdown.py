#!/usr/bin/python
#-*- coding: utf-8 -*-
import sys

from itsbox.operator import Config
from itsbox.util.MessageQueue import Rabbitmq as MessageQueueImpl
from itsbox.operator.Message import MgmtData


if __name__ == '__main__':
    if len(sys.argv) == 1:
        try:
            queue = MessageQueueImpl(Config.RABBITMQ_USER, Config.RABBITMQ_PASS, Config.RABBITMQ_IP, Config.RABBITMQ_PORT, Config.RABBITMQ_VHOST, heartbeat_interval=0)
            queue.create_send_channel(Config.RABBITMQ_QNAME_MGMT_IN, durable=True)
            send_msg = MgmtData()
            send_msg.set_op_action('stop')
            send_msg.set_op_target('all')
            send_msg.set_reply(False)
            queue.send(send_msg.get_json_data())
            print('Requested to stop the booted manager. The manager will be stopped after a while.')
        except BaseException as e:
            print('Exception occurred during starting up the manager : Exception="%s"' % e)
        finally:
            if queue:
                queue.close()
    else:
        print('Unknown argument or Too many arguments')
        print('USAGE : python %s' % sys.argv[0])

