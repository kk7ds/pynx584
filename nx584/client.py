import json
import requests
import time


class Client(object):
    def __init__(self, url):
        self._url = url
        self._session = requests.Session()
        self._last_event_index = 0

    def list_zones(self):
        r = self._session.get(self._url + '/zones')
        try:
            return r.json['zones']
        except TypeError:
            return r.json()['zones']

    def list_partitions(self):
        r = self._session.get(self._url + '/partitions')
        try:
            return r.json['partitions']
        except TypeError:
            return r.json()['partitions']

    def arm(self, armtype='auto'):
        if armtype not in ['stay', 'exit', 'auto']:
            raise Exception('Invalid arm type')
        r = self._session.get(
            self._url + '/command',
            params={'cmd': 'arm',
                    'type': armtype})
        return r.status_code == 200

    def disarm(self, master_pin):
        r = self._session.get(
            self._url + '/command',
            params={'cmd': 'disarm',
                    'master_pin': master_pin})
        return r.status_code == 200

    def set_bypass(self, zone, bypass):
        data = {'bypassed': bypass}
        r = self._session.put(self._url + '/zones/%i' % zone,
                              data=json.dumps(data),
                              headers={'Content-Type': 'application/json'})
        return r.status_code == 200

    def get_user(self, master_pin, user_number):
        params = {}
        while True:
            r = self._session.get(self._url + '/users/%i' % user_number,
                                  params=params,
                                  headers={'Master-Pin': master_pin})
            if r.status_code == 202:
                params['retry'] = 'yes'
                time.sleep(1)
                continue
            if r.status_code == 404:
                time.sleep(1)
                continue
            if r.status_code == 200:
                return r.json()
            print('Status code %i' % r.status_code)
            break

    def put_user(self, master_pin, user):
        cur_user = self.get_user(master_pin, user['number'])
        if not cur_user:
            return None
        r = self._session.put(self._url + '/users/%i' % user['number'],
                              headers={'Master-Pin': master_pin,
                                       'Content-Type': 'application/json'},
                              data=json.dumps(user))
        if r.status_code == 200:
            return r.json()

    def get_events(self, index=None, timeout=None):
        if index is None:
            index = self._last_event_index
        if timeout is None:
            timeout = 60
        r = self._session.get(self._url + '/events',
                              params={'index': index,
                                      'timeout': timeout})
        if r.status_code == 200:
            data = r.json()
            self._last_event_index = data['index']
            return data['events']

    def get_version(self):
        r = self._session.get(self._url + '/version')
        if r.status_code == 404:
            return '1.0'
        else:
            return r.json()['version']
