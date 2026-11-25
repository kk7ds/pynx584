import unittest
from unittest import mock

from nx584 import api
from nx584 import event_queue
from nx584 import model


class TestSystemEndpoint(unittest.TestCase):

    def setUp(self):
        api.app.config['TESTING'] = True
        self.client = api.app.test_client()

    @mock.patch.object(api, 'CONTROLLER')
    def test_system_endpoint_returns_json(self, mock_controller):
        mock_controller.system = model.System()
        mock_controller.system.panel_id = 42
        mock_controller.system.status_flags = ['AC fail', 'Low battery']

        response = self.client.get('/system')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')
        data = response.get_json()
        self.assertEqual(data['panel_id'], 42)
        self.assertEqual(data['status_flags'], ['AC fail', 'Low battery'])

    @mock.patch.object(api, 'CONTROLLER')
    def test_system_endpoint_empty_flags(self, mock_controller):
        mock_controller.system = model.System()
        mock_controller.system.panel_id = 0
        mock_controller.system.status_flags = []

        response = self.client.get('/system')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {'panel_id': 0, 'status_flags': []})

    def test_system_endpoint_controller_none(self):
        api.CONTROLLER = None

        with self.assertRaises(TypeError):
            self.client.get('/system')


class TestEventsEndpoint(unittest.TestCase):

    def setUp(self):
        api.app.config['TESTING'] = True
        self.client = api.app.test_client()
        self.queue = event_queue.EventQueue(100)
        for i in range(3):
            self.queue.push({'n': i})

    def _get(self, index):
        with mock.patch.object(api, 'CONTROLLER') as mock_controller:
            mock_controller.event_queue = self.queue
            response = self.client.get('/events?index=%i&timeout=0' % index)
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_events_new_since_index(self):
        data = self._get(1)
        self.assertEqual(data, {'events': [{'n': 1}, {'n': 2}], 'index': 3})

    def test_events_none_new_keeps_index(self):
        data = self._get(3)
        self.assertEqual(data, {'events': None, 'index': 3})

    def test_events_index_from_before_restart(self):
        # A client that talked to a previous run of the server still
        # holds a much higher index. It should be told our current index
        # instead of having it echoed back, so it picks up new events.
        data = self._get(16090)
        self.assertEqual(data, {'events': None, 'index': 3})
        self.queue.push({'n': 3})
        data = self._get(data['index'])
        self.assertEqual(data, {'events': [{'n': 3}], 'index': 4})


if __name__ == '__main__':
    unittest.main()
