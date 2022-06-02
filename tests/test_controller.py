import io
import unittest
import mock

from nx584 import controller

TESTFRAME = [1, 0x7e, 2, 0x7d, 3]


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
