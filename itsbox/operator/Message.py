#!/usr/bin/python
#-*- coding: utf-8 -*-
import copy
import json
import time


class AbstractData:
    json_data = None
    dict_data = {}
    changed = False

    def __init__(self):
        raise Exception('Abstract class cannot be instantiated.')

    def get_time(self, throw_if_absence=True):
        return float(self.dict_data['time']) if throw_if_absence else self.dict_data.get('time')

    def is_inbound_direction(self):
        flag = self.dict_data.get('direction')
        return True if flag is not None and flag == '1' else False

    def is_success(self):
        flag = self.dict_data.get('success')
        return True if flag is None or flag == '1' else False

    def get_message(self, throw_if_absence=True):
        return self.dict_data['msg'] if throw_if_absence else self.dict_data.get('msg')

    def is_operator_location(self):
        flag = self.dict_data.get('location')
        return False if flag is None or flag != '2' else True

    def need_reply(self):
        flag = self.dict_data.get('reply')
        return True if flag is None or flag == '1' else False

    def set_time(self, sec=None):
        self.dict_data['time'] = sec if sec is not None else str(int(time.time()))
        self.changed = True

    def set_direction(self, inbound=False):
        self.dict_data['direction'] = '1' if inbound else '2'
        self.changed = True

    def set_success(self, success=True):
        self.dict_data['success'] = '1' if success else '2'
        self.changed = True

    def set_message(self, msg):
        self.dict_data['msg'] = msg
        self.changed = True

    def set_location(self, operator=True):
        self.dict_data['location'] = '2' if operator else '1'
        self.changed = True

    def set_reply(self, need=True):
        self.dict_data['reply'] = '1' if need else '2'
        self.changed = True

    def decode(self):
        self.dict_data = json.loads(self.json_data)
        self.changed = False

    def encode(self):
        self.json_data = json.dumps(self.dict_data)
        self.changed = False

    def get_json_data(self):
        if self.changed:
            if self.dict_data is None or len(self.dict_data) == 0:
                raise Exception('No data to encode')
            self.encode()
        return self.json_data

    def get_dictionary_data(self):
        return self.dict_data

    def clone(self):
        return copy.deepcopy(self)


class TaskData(AbstractData):
    def __init__(self, json_string=None):
        if json_string:
            self.json_data = json_string
            self.decode()
        else:
            self.set_time()
            self.set_location()
            self.set_direction(True)

    def get_client_channel_id(self, throw_if_absence=True):
        return self.dict_data['client_channel_id'] if throw_if_absence else self.dict_data.get('client_channel_id')

    def get_company_code(self, throw_if_absence=True):
        return self.dict_data['company_code'] if throw_if_absence else self.dict_data.get('company_code')

    def get_op_code(self, throw_if_absence=True):
        return self.dict_data['op_code'] if throw_if_absence else self.dict_data.get('op_code')

    def get_op_data(self, throw_if_absence=True):
        return self.dict_data['op_data'] if throw_if_absence else self.dict_data.get('op_data')

    def set_client_channel_id(self, id):
        self.dict_data['client_channel_id'] = id
        self.changed = True

    def set_company_code(self, code):
        self.dict_data['company_code'] = code
        self.changed = True

    def set_op_code(self, code):
        self.dict_data['op_code'] = code
        self.changed = True

    def set_op_data(self, data):
        self.dict_data['op_data'] = data
        self.changed = True


class MgmtData(AbstractData):
    def __init__(self, json_string=None):
        if json_string:
            self.json_data = json_string
            self.decode()
        else:
            self.set_time()
            self.set_location()
            self.set_direction(True)

    def get_op_action(self, throw_if_absence=True):
        return self.dict_data['op_action'] if throw_if_absence else self.dict_data.get('op_action')

    def get_op_target(self, throw_if_absence=True):
        return self.dict_data['op_target'] if throw_if_absence else self.dict_data.get('op_target')

    def get_op_detail(self, throw_if_absence=True):
        return self.dict_data['op_detail'] if throw_if_absence else self.dict_data.get('op_detail')

    def set_op_action(self, action):
        self.dict_data['op_action'] = action
        self.changed = True

    def set_op_target(self, target):
        self.dict_data['op_target'] = target
        self.changed = True

    def set_op_detail(self, detail):
        self.dict_data['op_detail'] = detail
        self.changed = True


''' TaskData
{
  "time" : "123456789",
  "client_channel_id" : "",
  "company_code" : "1",
  "location" : "2",
  "direction" : "1",
  "op_code" : "AA001",
  "op_data" : "This is test message"
}
'''

''' MgmtData
{
  "time" : "123456789",
  "location" : "2",
  "direction": "1",
  "op_action" : "start",
  "op_target" : "worker",
  "op_detail" : "3(40)"
}
{
  "time" : "123456789",
  "location" : "2",
  "direction": "1",
  "op_action" : "stop",
  "op_target" : "all",
  "op_detail" : ""
}
{
  "time" : "123456789",
  "location" : "2",
  "direction": "1",
  "op_action" : "info",
  "op_target" : "worker",
  "op_detail" : "all"
}
'''