try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import logging
import serial
import time

import stevedore.extension

from nx584 import model


LOG = logging.getLogger('controller')


def parse_ascii(data):
    data_bytes = []
    for i in range(0, len(data), 2):
        data_bytes.append(int(data[i:i + 2], 16))
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
        return model.MSG_TYPES[self.msgtype]


class NXController(object):
    def __init__(self, port, baudrate, configfile):
        self._port = port
        self._baudrate = baudrate
        self._configfile = configfile
        self._ser = serial.Serial(port, baudrate, timeout=0.25)
        self._queue_waiting = False
        self._queue_should_wait = False
        self._queue = []
        self.zones = {}
        self.partitions = {}
        self.system = model.System()
        ext_mgr = stevedore.extension.ExtensionManager(
            'pynx584', invoke_on_load=True, invoke_args=(self,))
        self.extensions = [ext_mgr[name] for name in ext_mgr.names()]
        LOG.info('Loaded extensions %s' % ext_mgr.names())
        self._load_config()

    def _load_config(self):
        self._config = configparser.ConfigParser()
        self._config.read(self._configfile)

        if not self._config.has_section('config'):
            self._config.add_section('config')

        if self._config.has_section('zones'):
            for opt in self._config.options('zones'):
                number = int(opt)
                name = self._config.get('zones', opt)
                zone = self._get_zone(number)
                zone.name = name

    def _write_config(self):
        if not self._config.has_section('zones'):
            self._config.add_section('zones')

        for zone in self.zones.values():
            if (not self._config.has_option('zones', str(zone.number)) and
                    zone.name != 'Unknown'):
                self._config.set('zones', str(zone.number), zone.name)
        with open(self._configfile, 'w') as configfile:
            self._config.write(configfile)

    @property
    def interior_zones(self):
        return [x for x in self.zones.values() if 'Interior' in x.type_flags]

    @property
    def interior_bypassed(self):
        return all(['Inhibit' in x.condition_flags
                    for x in self.interior_zones])

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
        self._queue.append([0x23, number - 1])

    def arm_stay(self, partition=1):
        self._queue.append([0x3E, 0x00, partition])

    def arm_exit(self, partition=1):
        self._queue.append([0x3E, 0x02, partition])

    def arm_auto(self, partition=1):
        self._queue.append([0x3D, 0x05, 0x01, 0x01])

    def zone_bypass_toggle(self, zone):
        self._queue.append([0x3F, zone - 1])

    def get_system_status(self):
        self._queue.append([0x28])

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
        number = frame.data[0] + 1
        name = ''.join([chr(x) for x in frame.data[1:]])
        LOG.debug('Zone %i: %s' % (number, repr(name.strip())))
        self._get_zone(number).name = name.strip()
        LOG.debug('Zone info from %s' % self.zones.keys())
        self._write_config()

    def process_msg_4(self, frame):
        # Zone Status
        zone = self._get_zone(frame.data[0] + 1)
        condition = frame.data[5]
        types = frame.data[2:5]
        zone.state = bool(condition & 0x01)

        zone.condition_flags = []
        for index, string in enumerate(model.Zone.STATUS_FLAGS):
            if condition & (1 << index):
                zone.condition_flags.append(string)

        zone.type_flags = []
        for byte, flags in enumerate(model.Zone.TYPE_FLAGS):
            for bit, name in enumerate(flags):
                if types[byte] & (1 << bit):
                    zone.type_flags.append(name)

        LOG.info('Zone %i (%s) state is %s' % (
            zone.number, zone.name,
            zone.state and 'FAULT' or 'NORMAL'))
        LOG.debug('Zone %i (%s) %s %s' % (zone.number, zone.name,
                                          zone.condition_flags,
                                          zone.type_flags))
        for ext in self.extensions:
            ext.obj.zone_status(zone)

    def process_msg_6(self, frame):
        partition = self._get_partition(frame.data[0] + 1)
        types = frame.data[1:5] + frame.data[6:8]
        partition.condition_flags = []
        for byte, flags in enumerate(model.Partition.CONDITION_FLAGS):
            for bit, name in enumerate(flags):
                if types[byte] & (1 << bit):
                    partition.condition_flags.append(name)
        LOG.info('Partition %i %s' % (partition.number,
                                      partition.armed))
        LOG.debug('Partition %i %s' % (partition.number,
                                       partition.condition_flags))
        for ext in self.extensions:
            ext.obj.partition_status(partition)

    def process_msg_8(self, frame):
        errors = model.System.STATUS_FLAGS[1] + model.System.STATUS_FLAGS[2]
        status = frame.data[1:10]
        self.system.panel_id = frame.data[0]
        orig_flags = self.system.status_flags
        self.system.status_flags = []
        for byte, flags in enumerate(model.System.STATUS_FLAGS):
            for bit, name in enumerate(flags):
                if status[byte] & (1 << bit):
                    self.system.status_flags.append(name)
        LOG.debug('System status received (panel id 0x%02x)' % (
            self.system.panel_id))

        def _log(flag, asserted):
            if flag not in errors:
                fn = LOG.info
            else:
                if asserted:
                    fn = LOG.error
                else:
                    fn = LOG.warn
            if asserted:
                pfx = ''
            else:
                pfx = 'de-'
            msg = 'System %sasserts %s' % (pfx, flag)
            fn(msg)

        for flag in set(orig_flags) - set(self.system.status_flags):
            _log(flag, False)
        for flag in set(self.system.status_flags) - set(orig_flags):
            _log(flag, True)

        for ext in self.extensions:
            ext.obj.system_status(self.system)

    def process_msg_9(self, frame):
        commands = {0x28: 'on', 0x38: 'off'}
        house = chr(ord('A') + frame.data[0])
        unit = frame.data[1]
        cmd = commands.get(frame.data[2], frame.data[2])
        LOG.info('Device %s%02i command %s' % (house, unit, cmd))
        for ext in self.extensions:
            ext.obj.device_command(house, unit, cmd)

    def _run_queue(self):
        if not self._queue:
            return
        msg = self._queue.pop(0)
        LOG.debug('Sending queued %s' % msg)
        self._send(msg)

    def controller_loop(self):
        self.running = True

        self.send_nack()
        self.get_system_status()

        try:
            max_zone = self._config.getint('config', 'max_zone')
        except configparser.NoOptionError:
            max_zone = 8
            self._config.set('config', 'max_zone', str(max_zone))

        for i in range(1, max_zone + 1):
            if not self._config.has_option('zones', str(i)):
                self.get_zone_name(i)

        quiet_count = 0

        while self.running:
            frame = self.process_next()
            if frame is None:
                quiet_count += 1
                if quiet_count > 4:
                    self._run_queue()
                    quiet_count = 0
                continue
            quiet_count = 0
            LOG.debug('Received: %i %s (data %s)' % (frame.msgtype,
                                                     frame.type_name,
                                                     frame.data))
            if frame.ack_required:
                self.send_ack()
            else:
                self._run_queue()
            name = 'process_msg_%i' % frame.msgtype
            if hasattr(self, name):
                getattr(self, name)(frame)
