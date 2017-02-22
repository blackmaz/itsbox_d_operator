#!/usr/bin/python
#-*- coding: utf-8 -*-
import logging
import time

import pika
from pika.exceptions import ConnectionClosed

from itsbox.operator import Config

logger = logging.getLogger('util')
logger.setLevel(Config.LOG_LEVEL)
error_logger = logging.getLogger('error')


class BaseQueue:
    logger = None

    def send(self):
        pass

    def receive(self):
        pass

    def start_receive(self):
        pass

    def stop_receive(self):
        pass

    def publish(self):
        pass

    def subscribe(self):
        pass

    def start_subscribe(self):
        pass

    def stop_subscribe(self):
        pass

    def close(self):
        pass


class Rabbitmq(BaseQueue):
    exitFlag = False
    connection = None
    durable = False
    channel_send = None
    channel_recv = None
    channel_pub = None
    channel_sub = None
    queue = None
    exchange = None

    def __init__(self, userid, passwd, ip='localhost', port=5672, vhost='/', durable=False, heartbeat_interval=60):
        logger.debug('Creating Rabbitmq instance : user=%s, target=%s:%d, vhost=%s, durable=%s, hearbeat=%d' % (userid, ip, port, vhost, durable, heartbeat_interval))
        credentials = pika.PlainCredentials(userid, passwd)
        parameters = pika.ConnectionParameters(ip, port, vhost, credentials, heartbeat_interval=heartbeat_interval)
        self.durable = durable
        try:
            self.connection = pika.BlockingConnection(parameters)
            logger.debug('Created a queue connection : connection=%s' % self.connection)
        except ConnectionClosed as cc:
            logger.error('Failed to connect to queue : Address=%s:%d' % (ip, port))
            raise cc

    def create_send_channel(self, queue_name, durable=False):
        self.channel_send = self.connection.channel()
        self.qname_send = queue_name
        if durable == None:
            self.channel_send.queue_declare(queue=queue_name, durable=self.durable)
        else:
            self.channel_send.queue_declare(queue=queue_name, durable=durable)
        logger.debug('Created send channel : queue=%s, durable=%s' % (queue_name, durable))

    def create_receive_channel(self, queue_name, durable=False):
        self.channel_recv = self.connection.channel()
        self.qname_recv = queue_name
        if durable == None:
            self.queue = self.channel_recv.queue_declare(queue=queue_name, durable=self.durable)
        else:
            self.queue = self.channel_recv.queue_declare(queue=queue_name, durable=durable)
        logger.debug('Created receive channel : queue=%s, durable=%s' % (queue_name, durable))

    def create_publish_channel(self, exchange_name, exchange_type='fanout', durable=False):
        self.channel_pub = self.connection.channel()
        self.exname_pub = exchange_name
        if durable == None:
            self.channel_pub.exchange_declare(exchange=exchange_name, type=exchange_type, durable=self.durable)
        else:
            self.channel_pub.exchange_declare(exchange=exchange_name, type=exchange_type, durable=durable)
        logger.debug('Created publish channel : exchange=%s, type=%s, durable=%s' % (exchange_name, exchange_type, durable))

    def create_subscribe_channel(self, exchange_name, exchange_type='fanout', durable=False):
        self.channel_sub = self.connection.channel()
        self.exname_pub = exchange_name
        if durable == None:
            self.exchange = self.channel_sub.exchange_declare(exchange=exchange_name, type=exchange_type, durable=self.durable)
        else:
            self.exchange = self.channel_sub.exchange_declare(exchange=exchange_name, type=exchange_type, durable=durable)
        result = self.channel_sub.queue_declare(exclusive=True)
        self.qname_sub = result.method.queue
        self.channel_sub.queue_bind(exchange=exchange_name, queue=self.qname_sub)
        logger.debug('Created subscribe channel : exchange=%s, type=%s, durable=%s' % (exchange_name, exchange_type, durable))

    def send(self, msg):
        if self.channel_send == None:
            raise Exception('The send channel is null. Please create send channel first.')
        self.channel_send.basic_publish(exchange='', routing_key=self.qname_send, body=msg, properties=None)
        logger.debug('Sent a message : queue=%s, msg=%s' % (self.qname_send, msg))

    def receive(self, queue_name=None, no_ack=False):
        if self.channel_recv == None:
            raise Exception('The receive channel is null. Please create receive channel first.')
        if queue_name:
            method_frame, properties, body = self.channel_recv.basic_get(queue_name, no_ack=no_ack)
            if body and logger.isEnabledFor(logging.DEBUG):
                logger.debug('Received a message : queue=%s, no_ack=%s, msg=%s' % (queue_name, no_ack, body.replace('\r','\\r').replace('\n','\\n')))
        else:
            method_frame, properties, body = self.channel_recv.basic_get(self.qname_recv, no_ack=no_ack)
            if body and logger.isEnabledFor(logging.DEBUG):
                logger.debug('Received a message : queue=%s, no_ack=%s, msg=%s' % (self.qname_recv, no_ack, body.replace('\r','\\r').replace('\n','\\n')))
        return body

    def publish(self, msg):
        if self.channel_pub == None:
            raise Exception('The publish channel is null. Please create publish channel first.')
        self.channel_pub.basic_publish(exchange=self.exname_pub, routing_key='', body=msg)
        logger.debug('Published a message : exchange=%s, msg=%s' % (self.exname_pub, msg))

    def subscribe(self, queue_name=None, no_ack=False):
        if self.channel_sub == None:
            raise Exception('The subscribe channel is null. Please create subscribe channel first.')
        if queue_name:
            method_frame, properties, body = self.channel_sub.basic_get(queue_name, no_ack=no_ack)
            logger.debug('Subscribed a message : queue=%s, no_ack=%s, msg=%s' % (queue_name, no_ack, body))
        else:
            method_frame, properties, body = self.channel_sub.basic_get(self.qname_sub, no_ack=no_ack)
            logger.debug('Subscribed a message : queue=%s, no_ack=%s, msg=%s' % (self.qname_sub, no_ack, body))
        return body

    def purge(self, queue_name):
        self.channel_recv.queue_purge(queue_name)
        logger.warn('Purged message(s) : queue=%s, count=%s' % (queue_name, self.queue.method.message_count))

    def start_receive(self, callback, no_ack=False):
        if self.channel_recv == None:
            raise Exception('The receive channel is null. Please create receive channel first.')
        self.channel_recv.basic_consume(callback, queue=self.qname_recv, no_ack=no_ack)
        logger.debug('Starting to receive message continuously : queue=%s, no_ack=%s' % (self.qname_recv, no_ack))
        try:
            while self.channel_recv._consumer_infos:
                self.channel_recv.connection.process_data_events(time_limit=1)
        except KeyboardInterrupt:
            logger.info('Stopped to receive message in queue.')
        except BaseException as e:
            if str(e).find('Interrupted'):
                logger.warn('Interrupted to receive message : Exception=\'%s\'' % str(e))
            else:
                error_logger.exception('Error occurred during receiving message.')
                logger.error('Error occurred during receiving message : Exception=\'%s\'' % str(e))

    def stop_receive(self):
        if self.channel_recv == None:
            raise Exception('The receive channel is null. Please create receive channel first.')
        self.channel_recv.stop_consuming()
        logger.debug('Requested to stop to receive message continuously : queue=%s' % self.qname_recv)

    def start_subscribe(self, callback, no_ack=False):
        if self.channel_sub == None:
            raise Exception('The subscribe channel is null. Please create subscribe channel first.')
        self.channel_sub.basic_consume(callback, queue=self.qname_sub, no_ack=no_ack)
        logger.debug('Starting to subscribe message continuously : queue=%s, no_ack=%s' % (self.qname_sub, no_ack))
        try:
            while self.channel_sub._consumer_infos:
                self.channel_sub.connection.process_data_events(time_limit=1)
        except KeyboardInterrupt:
            logger.info('Stopped to receive message in queue.')
        except BaseException as e:
            if str(e).find('Interrupted'):
                logger.warn('Interrupted to receive message : Exception=\'%s\'' % str(e))
            else:
                error_logger.exception('Error occurred during receiving message.')
                logger.error('Error occurred during receiving message : Exception=\'%s\'' % str(e))

    def stop_subscribe(self):
        self.channel_sub.stop_consuming()
        logger.debug('Stopped to subscribe message continuously : queue=%s' % self.qname_sub)

    def close(self):
        if self.connection.is_open:
            logger.debug('Closing a queue connection : connection=%s' % self.connection)
            try:
                self.connection.close()
                logger.info('Closed a queue connection : Queue=%s' % self)
            except BaseException as e:
                logger.warn('Failed to close queue connection : Exception=\'%s\'' % e)
