try:
    import ConfigParser as configparser
except ImportError:
    import configparser
import datetime
import logging
import serial
import socket
import time

import stevedore.extension

from nx584 import event_queue
from nx584 import mail
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


def make_pin_buffer(digits):
    pinbuf = []
    for i in range(0, 6, 2):
        try:
            pinbuf.append((int(digits[i + 1]) << 4) | int(digits[i]))
        except (IndexError, TypeError):
            pinbuf.append(0xFF)
    return pinbuf


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
        self.msgtype = msgtypefield & 0x7F
        return self

    @property
    def type_name(self):
        return model.MSG_TYPES[self.msgtype]


class ConnectionLost(Exception):
    pass


class SocketWrapper(object):
    def __init__(self, portspec):
        self._portspec = portspec
        self.connect()

    def _connect(self):
        try:
            self._s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._s.connect(self._portspec)
            self._s.settimeout(0.5)
            return True
        except (socket.error, OSError) as ex:
            LOG.error('Failed to connect: %s' % ex)
            self._s = None
            return False

    def connect(self):
        while True:
            connected = self._connect()
            if connected:
                LOG.info('Connected')
                return True
            time.sleep(5)

    def write(self, buf):
        try:
            self._s.send(buf)
        except (socket.error, OSError):
            if self.connect():
                self._s.send(buf)
            else:
                LOG.error('Failed to send %r' % buf)

    def _readline(self):
        try:
            while True:
                c = self._s.recv(1).decode()
                if c == '\n':
                    break
                if c == '':
                    raise ConnectionLost()
                LOG.warning('Seeking (discarded %s %02x)' % (c, ord(c)))
        except socket.timeout:
            return ''

        start = time.time()
        line = ''
        while not line.endswith('\r'):
            c = self._s.recv(1).decode()
            if c is None:
                break
            line += c
            if time.time() - start > 60:
                LOG.error('Timeout reading a line, killing connection')
                self._s.close()
        return line

    def readline(self):
        try:
            return self._readline()
        except (socket.error, OSError, ConnectionLost):
            LOG.warning('Connection terminated')
            time.sleep(10)
            self.connect()
            return ''


class NXController(object):
    def __init__(self, portspec, configfile):
        self._portspec = portspec
        self._configfile = configfile
        self._queue_waiting = False
        self._queue_should_wait = False
        self._queue = []
        self.zones = {}
        self.partitions = {}
        self.users = {}
        self.system = model.System()
        ext_mgr = stevedore.extension.ExtensionManager(
            'pynx584', invoke_on_load=True, invoke_args=(self,))
        self.extensions = [ext_mgr[name] for name in ext_mgr.names()]
        LOG.info('Loaded extensions %s' % ext_mgr.names())
        self._load_config()
        self.event_queue = event_queue.EventQueue(100)
        self.connect()

    def connect(self):
        if '/' in self._portspec[0]:
            port, baudrate = self._portspec
            self._ser = serial.Serial(port, baudrate, timeout=0.25)
        else:
            self._ser = SocketWrapper(self._portspec)
            LOG.info('Connected')

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
        try:
            with open(self._configfile, 'w') as configfile:
                self._config.write(configfile)
        except IOError as ex:
            LOG.error('Unable to write %s: %s' % (self._configfile, ex))

    @property
    def interior_zones(self):
        return [x for x in self.zones.values() if 'Interior' in x.type_flags]

    @property
    def interior_bypassed(self):
        return all(['Inhibit' in x.condition_flags
                    for x in self.interior_zones])

    def process_next(self):
        data = self._ser.readline().strip()
        if not data:
            return None
        LOG.debug('Parsing raw ASCII line %r' % data)
        try:
            line = parse_ascii(data)
        except:
            LOG.exception('Failed to parse raw ASCII line %r' % data)
            return None
        frame = NXFrame.decode_line(line)
        return frame

    def _send(self, data):
        data.insert(0, len(data))
        data += fletcher(data)
        line = '\n%s\r' % make_ascii(data)
        self._ser.write(line.encode())

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

    def disarm(self, master_pin, partition=1):
        self._queue.append([0x3C] +
                           make_pin_buffer(master_pin) +
                           [0x01, partition])

    def zone_bypass_toggle(self, zone):
        self._queue.append([0x3F, zone - 1])

    def get_system_status(self):
        self._queue.append([0x28])

    def get_partition_status(self, partition):
        self._queue.append([0x26, partition - 1])

    def set_time(self):
        now = datetime.datetime.now()
        self._queue.append([0x3B,
                            now.year - 2000,
                            now.month,
                            now.day,
                            now.hour,
                            now.minute,
                            ((now.weekday() + 1) % 7) + 1])

    def get_user_info(self, master_pin, user_number):
        if len(master_pin) < 6:
            master_pin += '00'
        if len(master_pin) != 6:
            LOG.error('Master pin %r incorrect length' % master_pin)
            return False
        digits = make_pin_buffer(master_pin)
        self._queue.append([0x32] + digits + [user_number])
        LOG.debug('Sending for user info %s' % digits)
        return True

    def set_user_info(self, master_pin, user, changed):
        if user.number < 1:
            LOG.error('Unable to set PIN for user %i' % user.number)
            return False
        if 'pin' in changed:
            mstr_digits = make_pin_buffer(master_pin)
            user_digits = make_pin_buffer(user.pin)
            LOG.info('Setting user %i PIN to `%s`' % (
                user.number,
                ''.join(str(x) for x in user.pin if x < 10)))
            self._queue.append(
                [0x34] + mstr_digits + [user.number] + user_digits)
        return True

    def _get_zone(self, number):
        if number not in self.zones:
            self.zones[number] = model.Zone(number)
        return self.zones[number]

    def _get_partition(self, number):
        if number not in self.partitions:
            self.partitions[number] = model.Partition(number)
        return self.partitions[number]

    def _get_user(self, number):
        if number not in self.users:
            self.users[number] = model.User(number)
        return self.users[number]

    def process_msg_3(self, frame):
        # Zone Name
        number = frame.data[0] + 1
        name = ''.join([chr(x) for x in frame.data[1:]])
        LOG.info('Zone %i: %s' % (number, repr(name.strip())))
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
        event = {'type': 'zone_status',
                 'timestamp': datetime.datetime.now().isoformat(),
                 'zone': zone.number,
                 'zone_state': zone.state,
                 'zone_flags': zone.condition_flags,
             }
        self.event_queue.push(event)
        for ext in self.extensions:
            ext.obj.zone_status(zone)

    def _send_flag_notifications(self, flags_section, flags_key, asserted,
                                 deasserted, email_fn):
        changed = asserted | deasserted
        try:
            flags = set(self._config.get(flags_section,
                                         flags_key).split(','))
        except (configparser.NoOptionError, configparser.NoSectionError):
            flags = set([])

        if any([flag in changed for flag in flags]):
            if deasserted & flags:
                status = '(restored)'
            else:
                status = ''
            sub = '%s %s' % (list(changed & flags), status)
            msg = ('Asserted: %s\n' % (', '.join(asserted)) +
                   'Deasserted: %s\n' % (', '.join(deasserted)))
            email_fn(sub, msg)

    def process_msg_6(self, frame):
        partition = self._get_partition(frame.data[0] + 1)
        partition.last_user = frame.data[5]
        types = frame.data[1:5] + frame.data[6:8]
        was_armed = partition.armed
        orig_flags = partition.condition_flags
        partition.condition_flags = []
        for byte, flags in enumerate(model.Partition.CONDITION_FLAGS):
            for bit, name in enumerate(flags):
                if types[byte] & (1 << bit):
                    partition.condition_flags.append(name)
        if was_armed != partition.armed:
            LOG.info('Partition %i %s armed' % (
                partition.number,
                '' if partition.armed else 'not'))
        LOG.debug('Partition %i %s' % (partition.number,
                                       partition.condition_flags))
        for ext in self.extensions:
            ext.obj.partition_status(partition)

        deasserted = set(orig_flags) - set(partition.condition_flags)
        asserted = set(partition.condition_flags) - set(orig_flags)
        changed = asserted | deasserted

        event = {'type': 'partition',
                 'timestamp': datetime.datetime.now().isoformat(),
                 'partition': partition.number,
                 'partition_flags_asserted': list(asserted),
                 'partition_flags': partition.condition_flags,
                 'partition_was_armed': was_armed,
                 'partition_is_armed': partition.armed,
             }
        self.event_queue.push(event)

        if changed:
            mail.send_partition_email(self._config, partition,
                                      deasserted, asserted)

            def email_status(sub, msg):
                mail.send_partition_status_email(self._config, partition,
                                                 'status', sub, msg)

            def email_alarms(sub, msg):
                mail.send_partition_status_email(self._config, partition,
                                                 'alarms', sub, msg)

            section = 'partition_%i' % partition.number
            self._send_flag_notifications(section, 'status_flags', asserted,
                                          deasserted, email_status)
            self._send_flag_notifications(section, 'alarm_flags', asserted,
                                          deasserted, email_alarms)


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

        deasserted = set(orig_flags) - set(self.system.status_flags)
        asserted = set(self.system.status_flags) - set(orig_flags)

        for flag in deasserted:
            _log(flag, False)
        for flag in asserted:
            _log(flag, True)

        for ext in self.extensions:
            ext.obj.system_status(self.system)

        if asserted or deasserted:
            mail.send_system_email(self._config, deasserted, asserted)

        for i in range(1, 9):
            if ('Valid partition %i' % i) in asserted:
                LOG.debug('Requesting partition status for %i' % i)
                self.get_partition_status(i)

    def process_msg_9(self, frame):
        commands = {0x28: 'on', 0x38: 'off'}
        house = chr(ord('A') + frame.data[0])
        unit = frame.data[1]
        cmd = commands.get(frame.data[2], frame.data[2])
        LOG.info('Device %s%02i command %s' % (house, unit, cmd))
        event = {'type': 'device-command',
                 'timestamp': datetime.datetime.now().isoformat(),
                 'device': '%s%02i' % (house, unit),
                 'command': '%s' % cmd}
        self.event_queue.push(event)
        for ext in self.extensions:
            ext.obj.device_command(house, unit, cmd)

    def process_msg_10(self, frame):
        event = model.LogEvent()
        event.number = frame.data[0]
        event.log_size = frame.data[1]
        event.event_type = frame.data[2] & 0x7F
        event.reportable = bool(frame.data[2] & 0x80)
        event.zone_user_device = frame.data[3]
        event.partition_number = frame.data[4]
        month = frame.data[5]
        day = frame.data[6]
        hour = frame.data[7]
        minute = frame.data[8]
        now = datetime.datetime.now()
        if month > now.month:
            year = now.year - 1
        else:
            year = now.year
        event.timestamp = datetime.datetime(
            year=year, month=month, day=day,
            hour=hour, minute=minute)
        LOG.info('Log event: %s at %s' % (event.event_string,
                                          event.timestamp))
        _event = {'type': 'log',
                  'event': event.event_string,
                  'timestamp': event.timestamp.isoformat(),
              }
        self.event_queue.push(_event)
        for ext in self.extensions:
            ext.obj.log_event(event)

        mail.send_log_event_mail(self._config, event)

    def process_msg_18(self, frame):
        user = self._get_user(frame.data[0])
        user.pin = []
        user.authority_flags = []
        user.authorized_partitions = []
        for byte in frame.data[1:4]:
            user.pin.append(byte & 0x0F)
            user.pin.append((byte & 0xF0) >> 4)
        authbytetype = frame.data[4] & 0x80
        authbyte = frame.data[4] & 0x7F
        flags = model.User.AUTHORITY_FLAGS[1 if authbytetype else 0]
        for i, flag in enumerate(flags):
            if authbyte & (1 << i):
                user.authority_flags.append(flag)
        for i in range(0, 8):
            if frame.data[5] & (1 << i):
                user.authorized_partitions.append(i + 1)
        LOG.info('Received information about user %i' % user.number)

    def _run_queue(self):
        if not self._queue:
            return
        msg = self._queue.pop(0)
        LOG.debug('Sending queued %s' % msg)
        self._send(msg)

    def controller_loop(self):
        self.running = True

        self.set_time()

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
                pass
                # This is sometimes too fast if we get two responses
                # from a single command (like time set). Need to keep
                # track of waiting for replies and re-send things when
                # we don't hear back.
                # self._run_queue()
            name = 'process_msg_%i' % frame.msgtype
            if hasattr(self, name):
                try:
                    getattr(self, name)(frame)
                except Exception as e:
                    LOG.exception('Failed to process message type %i',
                                  frame.msgtype)
