import json
import requests


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
