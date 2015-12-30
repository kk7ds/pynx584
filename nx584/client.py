import json
import requests
import time


class Client(object):
    def __init__(self, url):
        self._url = url
        self._session = requests.Session()

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

    def set_bypass(self, zone, bypass):
        data = {'bypassed': bypass}
        r = self._session.put(self._url + '/zones/%i' % zone,
                              data=json.dumps(data),
                              headers={'Content-Type': 'application/json'})
        return r.status_code == 200

    def get_user(self, master_pin, user_number):
        tried = False
        while True:
            r = self._session.get(self._url + '/users/%i' % user_number,
                                  headers={'Master-Pin': master_pin})
            if r.status_code == 204:
                if tried:
                    print('Failed to retrieve info for user')
                    break
                tried = True
                time.sleep(5)
                continue
            if r.status_code == 200:
                return r.json()
            print('Status code %i' % r.status_code)
            break

    def put_user(self, master_pin, user):
        r = self._session.put(self._url + '/users/%i' % user['number'],
                              headers={'Master-Pin': master_pin,
                                       'Content-Type': 'application/json'},
                              data=json.dumps(user))
        return r.status_code < 300
