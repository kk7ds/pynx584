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

    def arm(self, stay=False):
        r = self._session.get(
            self._url + '/command',
            params={'cmd': 'arm',
                    'type': stay and 'stay' or 'exit'})
        return r.status_code == 200
