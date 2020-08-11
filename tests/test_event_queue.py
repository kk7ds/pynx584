import unittest
import mock

from nx584 import event_queue


class TestEventQueue(unittest.TestCase):
    def test_push(self):
        eq = event_queue.EventQueue(10)
        eq.push('a')
        eq.push('b')
        self.assertEqual(['a', 'b'], [x.payload for x in eq.get(0)])
        c = eq.current
        eq.push('c')
        self.assertEqual(['c'], [x.payload for x in eq.get(c)])

    def test_trim(self):
        eq = event_queue.EventQueue(5)
        for i in range(1, 11):
            eq.push(i)
        self.assertEqual(10, eq.current)
        self.assertEqual([6, 7, 8, 9, 10],
                         [x.payload for x in eq._queue])
        self.assertEqual([6, 7, 8, 9, 10],
                         [x.payload for x in eq.get(0)])
        self.assertEqual([6, 7, 8, 9, 10],
                         [x.payload for x in eq.get(3)])
        self.assertEqual([8, 9, 10],
                         [x.payload for x in eq.get(7)])

    def test_get(self):
        eq = event_queue.EventQueue(10)
        eq.push(1)
        cur = eq.current
        with mock.patch.object(eq, '_condition') as mock_c:
            eq.get(cur)
            mock_c.wait.assert_called_once_with(None)
        with mock.patch.object(eq, '_condition') as mock_c:
            eq.get(0)
            self.assertFalse(mock_c.wait.called)

    def test_get_empty(self):
        eq = event_queue.EventQueue(10)
        c = eq.current
        with mock.patch.object(eq, '_condition') as mock_c:
            self.assertEqual(None, eq.get(c))
            mock_c.wait.assert_called_once_with(None)
        eq.push(1)
        with mock.patch.object(eq, '_condition') as mock_c:
            self.assertEqual(1, eq.get(c)[0].payload)
            self.assertFalse(mock_c.called)
        c = eq.current
        with mock.patch.object(eq, '_condition') as mock_c:
            self.assertEqual(None, eq.get(c))
            mock_c.wait.assert_called_once_with(None)
