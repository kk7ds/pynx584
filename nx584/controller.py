import serial
import time

from nx584 import model


MSG_TYPES = [
    'UNUSED',
    'Interface Configuration',
    'Reserved',
    'Zone Name',
    'Zone Status',
    'Zones Snapshot',
    'Partition Status',
    'Partitions Snapshot',
    'System Status',
    'X-10 Message Received',
    'Log Event',
    'Keypad Message Received',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Program Data Reply',
    'Reserved',
    'User Information Reply',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Reserved',
    'Command Failed',
    'Positive Acknowledge',
    'Negative Acknowledge',
    'Message Rejected',
    # 0x20
    'Reserved',
    'Interface Configuration Request',
    'Reserved',
    'Zone Name Request',
    'Zone Status Request',
    'Zones Snapshot Request',
    'Partition Status Request',
    'Partitions Snapshot Request',
    'System Status Request',
    'Send X-10 Message',
    'Log Event Request',
    'Send Keypad Text Message',
    'Keypad Terminal Mode REquest',
    'Reserved',
    'Reserved',
    'Reserved',
    'Program Data Request',
    'Program Data Command',
    'User Information Request with PIN',
    'User Information Request without PIN',
    'Set User Code Command with PIN',
    'Set User Code Command without PIN',
    'Set User Authorization Command with PIN',
    'Set User Authorization Command without PIN',
    'Reserved',
    'Reserved',
    'Store Communication Event Command',
    'Set Clock / Calendar Command',
    'Primary Keypad Function with PIN',
    'Primary Keypad Function without PIN',
    'Secondary Keypad Function',
    'Zone Bypass Toggle',
]


def parse_ascii(data):
    data_bytes = []
    for i in range(0, len(data), 2):
        data_bytes.append(int(data[i:i+2], 16))
    return data_bytes


def make_ascii(data):
    data_chars = []
    for b in data:
        data_chars.append('%02X' % b)
    return ''.join(data_chars)


def fletcher(data, k=16):
    if  k not in (16, 32, 64):
        raise ValueError("Valid choices of k are 16, 32 and 64")
    nbytes = k // 16
    mod = 2 ** (8 * nbytes) - 1
    s = s2 = 0
    for t in data:
        s += t
        s2 += s
    cksum = s % mod + (mod + 1) * (s2 % mod)
    sum1 = cksum & 0xFF
    sum2 = (cksum & 0xFF00) >> 8
    return sum1, sum2


class NXFrame(object):
    def __init__(self):
        self.length = 0
        self.msgtype = 0
        self.checksum = 0
        self.data = []
        self.ackreq = False

    @property
    def ack_required(self):
        return self.ackreq

    @staticmethod
    def decode_line(line_bytes):
        self = NXFrame()
        self.length = line_bytes[0]
        msgtypefield = line_bytes[1]
        self.checksum = (line_bytes[-2] << 8) & line_bytes[-1]
        self.data = line_bytes[2:-2]
        self.ackreq = bool(msgtypefield & 0x80)
        self.msgtype = msgtypefield & 0x3F
        return self

    @property
    def type_name(self):
        return MSG_TYPES[self.msgtype]


class NXController(object):
    def __init__(self, port, baudrate):
        self._port = port
        self._baudrate = baudrate
        self._ser = serial.Serial(port, baudrate, timeout=0.25)
        self._queue_waiting = False
        self._queue_should_wait = False
        self._queue = []
        self.zones = {}
        self.partitions = {}

    def process_next(self):
        line = parse_ascii(self._ser.readline().strip())
        if not line:
            return None
        frame = NXFrame.decode_line(line)
        return frame

    def _send(self, data):
        data.insert(0, len(data))
        data += fletcher(data)
        self._ser.write('\n%s\r' % make_ascii(data))

    def send_ack(self):
        self._send([0x1D])

    def send_nack(self):
        self._send([0x1E])

    def get_zone_name(self, number):
        self._queue.append([0x23, number])

    def arm_stay(self, partition=1):
        self._queue.append([0x3E, 0x00, partition])

    def arm_exit(self, partition=1):
        self._queue.append([0x3E, 0x02, partition])

    def _get_zone(self, number):
        if number not in self.zones:
            self.zones[number] = model.Zone(number)
        return self.zones[number]

    def _get_partition(self, number):
        if number not in self.partitions:
            self.partitions[number] = model.Partition(number)
        return self.partitions[number]

    def process_msg_3(self, frame):
        # Zone Name
        number = frame.data[0]
        name = ''.join([chr(x) for x in frame.data[1:]])
        print 'Zone %i: %s' % (number, repr(name.strip()))
        self._get_zone(number).name = name.strip()
        print 'Zone info from %s' % self.zones.keys()

    def process_msg_4(self, frame):
        # Zone Status
        zone = self._get_zone(frame.data[0])
        condition = frame.data[5]
        types = frame.data[2:5]
        zone.status = bool(condition & 0x01)

        status_flags = [
            'Faulted', 'Trouble', 'Bypass',
            'Inhibit', 'Low battery', 'Loss of supervision',
            'Reserved']
        zone.condition_flags = []
        for index, string in enumerate(status_flags):
            if condition & (1 << index):
                zone.condition_flags.append(string)

        zone.type_flags = []
        type_flags = [
            ['Fire', '24 hour', 'Key-switch', 'Follower',
             'Entry / exit delay 1', 'Entry / exit delay 2',
             'Interior', 'Local only'],
            ['Keypad sounder', 'Yelping Siren', 'Steady Siren',
             'Chime', 'Bypassable', 'Group bypassable', 'Force armable',
             'Entry guard'],
            ['Fast loop response', 'Double EOL tamper', 'Trouble',
             'Cross zone', 'Dialer delay', 'Swinger shutdown',
             'Restorable', 'Listen in'],
        ]
        for byte, flags in enumerate(type_flags):
            for bit, name in enumerate(flags):
                if types[byte] & (1 << bit):
                    zone.type_flags.append(name)

        print 'Zone %i %s status %s (%s) (%s)' % (zone.number,
                                                  zone.name,
                                                  zone.status,
                                                  zone.condition_flags,
                                                  zone.type_flags)

    def process_msg_6(self, frame):
        condition_flags = [
            ['Bypass code required', 'Fire trouble', 'Fire',
             'Pulsing buzzer', 'TLM fault memory', 'reserved',
             'Armed', 'Instant'],
            ['Previous alarm', 'Siren on', 'Steady siren on',
             'Alarm memory', 'Tamper', 'Cancel command entered',
             'Code entered', 'Cancel pending'],
            ['Reserved', 'Silent exit enabled', 'Entryguard (stay mode)',
             'Chime mode on', 'Entry', 'Delay expiration warning',
             'Exit 1', 'Exit 2'],
            ['LED extinguish', 'Cross timing', 'Recent closing being timed',
             'Reserved', 'Exit error triggered', 'Auto home inhibited',
             'Sensor low battery', 'Sensor lost supervision'],
            ['Zone bypassed', 'Force arm triggered by auto arm',
             'Ready to arm', 'Ready to force arm', 'Valid PIN accepted',
             'Chime on (sounding)', 'Error beep (triple beep)',
             'Tone on (activation tone)'],
            ['Entry 1', 'Open period', 'Alarm sent using phone number 1',
             'Alarm sent using phone number 2',
             'Alarm sent using phone number 3',
             'Cancel report is in the stack',
             'Keyswitch armed', 'Delay trip in progress (common zone)'],
        ]
        partition = self._get_partition(frame.data[0])
        types = frame.data[1:5] + frame.data[6:8]
        partition.condition_flags = []
        for byte, flags in enumerate(condition_flags):
            for bit, name in enumerate(flags):
                if types[byte] & (1 << bit):
                    partition.condition_flags.append(name)
        print 'Partition %i status %s' % (partition.number,
                                          partition.condition_flags)

    def _run_queue(self):
        if not self._queue:
            #print 'Nothing queued'
            return
        msg = self._queue.pop(0)
        print 'Sending queued %s' % msg
        self._send(msg)

    def controller_loop(self):
        self.running = True

        self.send_nack()
        print 'Trashing %s' % self.process_next()

        for i in range(0, 16):
            self.get_zone_name(i)

        #self.arm_stay()

        quiet_count = 0

        while self.running:
            frame = self.process_next()
            if frame is None:
                quiet_count += 1
                if quiet_count > 4:
                    #print 'Running queue because frame is %s' % frame
                    self._run_queue()
                    quiet_count = 0
                continue
            quiet_count = 0
            print('Received: %i %s' % (frame.msgtype,
                                       frame.type_name))
            if frame.ack_required:
                self.send_ack()
            else:
                #print 'Running queue because non-ack reply received'
                self._run_queue()
            name = 'process_msg_%i' % frame.msgtype
            if hasattr(self, name):
                getattr(self, name)(frame)
