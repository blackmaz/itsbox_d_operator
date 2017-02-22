#!/usr/bin/python
#-*- coding: utf-8 -*-
from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider


class AWS:
    driverInstance = None
    accessKey = None
    secretKey = None
    regionName = None
    secure = False
    proxyUrl = None
    network = None
    security = None

    node = None
    loadBalance = None

    def __init__(self, access_key, secret_key=None, region_name=None, secure=False, proxy_url=None):
        self.accessKey = access_key
        self.secretKey = secret_key
        self.regionName = region_name
        self.secure = secure
        self.driverInstance = get_driver(Provider.EC2)(key=self.accessKey, secret=self.secretKey, secure=self.secure, region=self.regionName)
        if proxy_url:
            self.driverInstance.connection.set_http_proxy(proxy_url=proxy_url)
            self.proxyUrl = proxy_url
        self.network = self.Network(self)
        self.security = self.Security(self)
        self.node = self.Node(self)
        self.loadBalance = self.LoadBalance(self)

    @staticmethod
    def list_regions():
        aws_regions = [
            'ap-south-1',
            'eu-west-2',
            'eu-west-1',
            'ap-northeast-2',
            'ap-northeast-1',
            'sa-east-1',
            'ca-central-1',
            'ap-southeast-1',
            'ap-southeast-2',
            'eu-central-1',
            'us-east-1',
            'us-east-2',
            'us-west-1',
            'us-west-2'
        ]
        return aws_regions

    def list_sizes(self):
        return self.driverInstance.list_sizes()


    class Network:
        def __init__(self, super):
            self.super = super

        def test(self):
            print('network in awk : driver=%s' % self.super.driverInstance)


    class Security:
        def __init__(self, super):
            self.super = super

        def test(self):
            print('security in awk : driver=%s' % self.super.driverInstance)


    class Node:
        def __init__(self, super):
            self.super = super

        def test(self):
            print('node in awk : driver=%s' % self.super.driverInstance)


    class LoadBalance:
        def __init__(self, super):
            self.super = super

        def test(self):
            print('lb in awk : driver=%s' % self.super.driverInstance)
