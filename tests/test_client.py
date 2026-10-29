import unittest
from unittest import mock

from nx584 import client


class TestClientTimeout(unittest.TestCase):
    def _client(self, timeout=None):
        with mock.patch('requests.Session') as mock_session:
            session = mock_session.return_value
            session.get.return_value.status_code = 200
            session.get.return_value.json.return_value = {
                'index': 1, 'events': [], 'version': '1.1'}
            session.put.return_value.status_code = 200
            if timeout is None:
                clnt = client.Client('http://localhost:5007')
            else:
                clnt = client.Client('http://localhost:5007',
                                     timeout=timeout)
        return clnt, session

    def _call_all(self, clnt):
        clnt.list_zones()
        clnt.list_partitions()
        clnt.arm()
        clnt.disarm('1234')
        clnt.set_bypass(1, True)
        clnt.get_user('1234', 1)
        clnt.put_user('1234', {'number': 1})
        clnt.get_version()
        clnt.get_system()
        clnt.get_info()

    def _timeouts(self, session):
        calls = session.get.call_args_list + session.put.call_args_list
        self.assertEqual(11, len(calls))
        return [c.kwargs.get('timeout', 'missing') for c in calls]

    def test_no_timeout_by_default(self):
        clnt, session = self._client()
        self._call_all(clnt)
        self.assertEqual([None] * 11, self._timeouts(session))

    def test_timeout(self):
        clnt, session = self._client(timeout=10)
        self._call_all(clnt)
        self.assertEqual([10] * 11, self._timeouts(session))

    def test_get_events_no_timeout_by_default(self):
        clnt, session = self._client()
        clnt.get_events()
        session.get.assert_called_once_with(
            'http://localhost:5007/events',
            params={'index': 0, 'timeout': 60},
            timeout=None)

    def test_get_events_adds_long_poll_timeout(self):
        clnt, session = self._client(timeout=10)
        clnt.get_events()
        session.get.assert_called_once_with(
            'http://localhost:5007/events',
            params={'index': 0, 'timeout': 60},
            timeout=70)

    def test_get_events_adds_explicit_long_poll_timeout(self):
        clnt, session = self._client(timeout=10)
        clnt.get_events(index=5, timeout=30)
        session.get.assert_called_once_with(
            'http://localhost:5007/events',
            params={'index': 5, 'timeout': 30},
            timeout=40)

    def test_request_exception_propagates(self):
        clnt, session = self._client(timeout=10)
        session.get.side_effect = client.requests.exceptions.Timeout
        self.assertRaises(client.requests.exceptions.Timeout,
                          clnt.list_zones)
