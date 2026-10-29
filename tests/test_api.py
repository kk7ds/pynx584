import unittest
from unittest import mock

from nx584 import api
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


if __name__ == '__main__':
    unittest.main()
