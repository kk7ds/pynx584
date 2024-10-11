import io
import logging
import unittest
import tempfile
from unittest import mock

from nx584 import controller

TESTFRAME = [1, 0x7e, 2, 0x7d, 3]
logging.basicConfig(level=logging.DEBUG)


class TestProtocols(unittest.TestCase):
    def test_write_ascii(self):
        stream = io.BytesIO()
        proto = controller.NXASCII(stream)

        # Write a test frame
        proto.write_frame(TESTFRAME)

        # Make sure that the stream got the actual bytes expected
        length = len(TESTFRAME)
        s1, s2 = controller.fletcher([length] + TESTFRAME)
        self.assertEqual(b'\n%02x017E027D03%02x%02x\r' % (length, s1, s2),
                         stream.getvalue())

        # Reset the stream and read it back
        stream.seek(0)
        data = proto.read_frame()

        # Make sure we got the right length, data, and checksum
        self.assertEqual(data, [length] + TESTFRAME + [s1, s2])

    def test_write_binary(self):
        stream = io.BytesIO()
        proto = controller.NXBinary(stream)

        # Write a test frame
        proto.write_frame(TESTFRAME)

        # Make sure that the stream got the actual bytes expected
        length = len(TESTFRAME)
        s1, s2 = controller.fletcher([length] + TESTFRAME)
        self.assertEqual(b'\x7e' + bytes([length]) +
                         b'\x01\x7d\x5e\x02\x7d\x5d\x03' + bytes([s1, s2]),
                         stream.getvalue())

        # Reset the stream and read it back
        stream.seek(0)
        data = proto.read_frame()

        # Make sure we got the right length, data, and checksum
        self.assertEqual(data, [length] + TESTFRAME + [s1, s2])


class SplitIO(io.BytesIO):
    def __init__(self, r, w):
        self.r = r
        self.w = w

    def read(self, n):
        return self.r.read(n)

    def write(self, b):
        return self.w.write(b)


def get_wrapper(config):
    rio = io.BytesIO()
    wio = io.BytesIO()

    class FakeWrapper(controller.StreamWrapper):
        def _connect(self):
            self._s = SplitIO(rio, wio)
            return True

    return rio, wio, FakeWrapper('fakeport', config)


class TestController(unittest.TestCase):
    def setUp(self):
        with mock.patch('stevedore.extension.ExtensionManager'):
            with tempfile.NamedTemporaryFile() as f:
                self.ctrl = controller.NXController('fakeport', f.name)

    def _run_until_idle(self):
        def stop():
            self.ctrl.running = False

        self.ctrl.running = True
        self.ctrl._idle_time_heartbeat_seconds = 0.1
        self.ctrl._config.set('config', 'max_zone', '2')

        with mock.patch.object(self.ctrl, 'generate_heartbeat_activity',
                               side_effect=stop):
            self.ctrl.controller_loop()

    def _test_startup(self, binary):
        fake_config = mock.MagicMock()
        fake_config.getboolean.return_value = binary
        rio, wio, self.ctrl._ser = get_wrapper(fake_config)

        self._run_until_idle()

        expected = [
            '0128292A',   # system status
            '022400264E', # zone 1 status
            '022300254C', # zone 1 name
            '022401274F', # zone 2 status
            '022301264D', # zone 2 name
        ]

        return expected, wio

    def test_startup_ascii(self):
        expected, wio = self._test_startup(False)

        messages = wio.getvalue().split(b'\r')

        # First message is the time/date, which will vary. Make sure
        # it looks sane
        self.assertTrue(messages[0].startswith(b'\n073B'))

        # Check the rest of the messages to make sure they look like
        # we expect
        self.assertEqual([b'\n%s' % m.encode() for m in expected],
                         messages[1:-1])

    def test_startup_binary(self):
        expected, wio = self._test_startup(True)

        # Use the NXBinary proto adapter to read the stream so we can
        # compare to the same list of expected messages.
        wio.seek(0)
        proto = controller.NXBinary(wio)

        messages = []
        while True:
            try:
                frame = proto.read_frame()
                messages.append(controller.make_ascii(frame))
            except controller.ReadTimeout:
                break

        # First message is the time/date, which will vary. Make sure
        # it looks sane
        self.assertTrue(messages[0].startswith('073B'))

        # Check the rest of the messages to make sure they look like
        # we expect
        self.assertEqual(expected, messages[1:])

    def _test_receive(self, binary):
        fake_config = mock.MagicMock()
        fake_config.getboolean.return_value = binary
        rio, wio, self.ctrl._ser = get_wrapper(fake_config)

        messages = [
            # Partitions status
            [0x87, 0x47, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
            # Partitions snapshot
            [0x86, 0x00, 0x68, 0x00, 0xE0, 0x40, 0x62, 0x04, 0x82, 0x02, 0x07],
            # Partitions status
            [0x87, 0x47, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
        ]

        if binary:
            proto = controller.NXBinary(rio)
        else:
            proto = controller.NXASCII(rio)

        for message in messages:
            proto.write_frame(message)
        rio.seek(0)

        self.ctrl.process_msg_7 = None
        with mock.patch.object(self.ctrl, 'process_msg_7') as pm:
            with mock.patch.object(self.ctrl, 'send_ack') as sa:
                self._run_until_idle()
                self.assertEqual(2, pm.call_count)
                sa.assert_has_calls([mock.call(), mock.call()])

        return rio.getvalue()

    def test_receive_ascii(self):
        buf = self._test_receive(False)
        print('Test buffer is %r' % buf)

    def test_receive_binary(self):
        buf = self._test_receive(True)
        print('Test buffer is %r' % list(buf))
