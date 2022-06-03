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

        s1, s2 = fletcher(line_bytes[:-2])
        if [s1, s2] != line_bytes[-2:]:
            raise ReadFailure('Checksum mismatch on received frame')

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


class ReadTimeout(Exception):
    pass


class ConnectionLost(Exception):
    pass


class ReadFailure(Exception):
    pass


class NXProtocol(object):
    """Abstract the act of talking to the control panel."""
    def __init__(self, stream):
        self.stream = stream

    def read(self, n):
        """Read bytes from the stream.

        Does the right thing for sockets and serial ports.

        :raises: ReadTimeout if there is no data
        :raises: ConnectionLost if something goes wrong
        """
        if hasattr(self.stream, 'read'):
            r = self.stream.read(n)
            if r == b'':
                raise ReadTimeout()
            return r
        elif hasattr(self.stream, 'recv'):
            try:
                r = self.stream.recv(n)
            except socket.timeout:
                raise ReadTimeout()
            except (socket.error, OSError):
                raise ConnectionLost()
            if r == b'':
                raise ConnectionLost()
            return r
        else:
            raise ConnectionLost('What is this stream?')

    def write(self, data):
        """Write bytes to the stream.

        :raises: ConnectionLost if something goes wrong
        """
        if hasattr(self.stream, 'write'):
            self.stream.write(data)
        elif hasattr(self.stream, 'send'):
            try:
                self.stream.send(data)
            except (socket.error, OSError):
                raise ConnectionLost()
        else:
            raise ConnectionLost('What is this stream?')

    def discard_until(self, byte):
        """Reads any unexpected data until we encounter an expected byte.

        :raises: ReadTimeout (via self.read()) if we never get it.
        """
        while True:
            c = self.read(1)
            if c == byte:
                return c
            LOG.warning('Seeking (discarded %s %02x)' % (c, c[0]))

    def read_frame(self):
        """Read a whole frame from the stream.

        :returns: An array of int values, inclusive of the length and checksum
                  bytes
        :raises: ConnectionLost if something goes wrong or the stream cannot
                 be parsed
        """
        return []

    def write_frame(self, data):
        """Write a whole frame to the stream.

        NOTE: This adds the length and checksum bytes automatically.

        :param: data is an array of integers
        """
        pass


class NXASCII(NXProtocol):
    def read_frame(self):
        self.discard_until(b'\n')

        start = time.time()
        line = ''
        while not line.endswith('\r'):
            try:
                c = self.read(1).decode()
            except ReadTimeout:
                LOG.error('Mid-frame read timeout (got %i: %r)' % (
                    len(line), line))
                raise ConnectionLost()
            line += c
            if time.time() - start > 60:
                LOG.error('Timeout reading a line, killing connection')
                raise ConnectionLost()

        LOG.debug('Parsing ASCII frame %r' % line.strip())
        try:
            return parse_ascii(line.strip())
        except Exception:
            LOG.exception('Failed to parse raw ASCII line %r' % line.strip())
            raise ConnectionLost()

    def write_frame(self, data):
        data = [len(data)] + data
        data += fletcher(data)
        raw = '\n%s\r' % make_ascii(data)
        self.write(raw.encode())


class NXBinary(NXProtocol):
    def read_frame(self):
        self.discard_until(b'\x7e')

        length = self.read(1)[0]
        buffer = [length]
        start = time.time()

        bytestuffed = False

        i = 1
        while (i <= length + 2):
            try:
                c = self.read(1)[0]
            except ReadTimeout:
                LOG.error('Mid-frame read timeout (expected %i got %i)' % (
                    length, i))
                raise ConnectionLost()

            if c == 0x7e:
                raise ConnectionLost('Received start byte mid-frame!')

            # Adjust any byte stuffed bytes - Skip the current byte if so,
            # then XOR the following byte with 0x20
            if c == 0x7d:
                bytestuffed = True
            else:
                if bytestuffed:
                    c = c ^ 0x20
                    bytestuffed = False
                buffer.append(c)
                i += 1

            if time.time() - start > 60:
                LOG.error('Timeout reading a line, killing connection')
                raise ConnectionLost()

        return buffer

    def write_frame(self, data):
        data = [len(data)] + data
        data += fletcher(data)
        # Byte Stuff Any 0x7d, 0x7e bytes
        bytestuff = [i for i, x in enumerate(data) if x == 0x7d]
        for i, index in reversed(list(enumerate(bytestuff))):
            data[index:index+1] = [0x7d, 0x5d]
        bytestuff = [i for i, x in enumerate(data) if x == 0x7e]
        for i, index in reversed(list(enumerate(bytestuff))):
            data[index:index+1] = [0x7d, 0x5e]

        # add the start character 0x7e
        data.insert(0, 0x7e)

        self.write(bytes(data))


class StreamWrapper(object):
    """Wraps a connection to the control panel.

    This mostly just manages connecting, reconnecting, and some error handling,
    transparent to the protocol (ASCII or Binary) being used.
    """
    def __init__(self, portspec, config):
        self._portspec = portspec
        self._config = config

        try:
            self._use_binary_protocol = self._config.getboolean(
                'config', 'use_binary_protocol')
        except configparser.NoOptionError:
            self._use_binary_protocol = False

        self._s = None
        self.protocol = None
        self.connect()

    def connect(self):
        sleep_time = 0
        while True:
            connected = self._connect()
            if connected:
                if self._use_binary_protocol:
                    self.protocol = NXBinary(self._s)
                else:
                    self.protocol = NXASCII(self._s)
                LOG.info('Connected')
                return True
            sleep_time = min(60, sleep_time + 5)
            LOG.debug('Waiting %i sec before retry...' % sleep_time)
            time.sleep(sleep_time)

    def reconnect(self):
        self._s.close()
        time.sleep(10)
        self.connect()

    def read_frame_raw(self):
        """Read a raw frame from the stream.

        Returns the raw bytes (inclusive of length and checksum) or None
        if there is no data to read.
        """
        try:
            return self.protocol.read_frame()
        except ConnectionLost as e:
            LOG.warning('Connection terminated: %s' % e)
            self.reconnect()
            return None
        except ReadTimeout:
            return None
        except UnicodeDecodeError as e:
            LOG.error('Failed to decode a line; reconnecting: %s' % e)
            return None

    def write_frame_raw(self, data):
        """Writes a frame to the stream.

        NOTE: length and checksum values are added automatically.
        """
        try:
            self.protocol.write_frame(data)
        except ConnectionLost:
            LOG.warning('Failed to send frame; reconnecting')
            self.reconnect()
            # Try to re-send if we reconnect so we don't lose this event
            self.protocol.write(data)


class SocketWrapper(StreamWrapper):
    def _connect(self):
        if self._s:
            self._s.close()
        try:
            self._s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            LOG.debug('Connecting...')
            self._s.connect(self._portspec)
            self._s.settimeout(0.5)
            return True
        except (socket.error, OSError) as ex:
            LOG.error('Failed to connect: %s' % ex)
            self._s = None
            self.protocol = None
            return False


class SerialWrapper(StreamWrapper):
    def _connect(self):
        port, baudrate = self._portspec
        self._s = serial.Serial(port, baudrate, timeout=0.25)


class NXController(object):
    def __init__(self, portspec, configfile):
        self._portspec = portspec
        self._configfile = configfile
        self._queue_waiting = False
        self._queue_should_wait = False
        self._queue = []
        self.last_active = 0
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
        try:
            self.zone_name_update = self._config.getboolean('config', 'zone_name_update')
        except configparser.NoOptionError:
            self.zone_name_update = True
        try:
            self._idle_time_heartbeat_seconds = self._config.getint(
                'config', 'idle_time_heartbeat_seconds')
        except configparser.NoOptionError:
            self._idle_time_heartbeat_seconds = 120

    def connect(self):
        if '/' in self._portspec[0] or 'COM' in self._portspec[0]:
            self._ser = SerialWrapper(self._portspec, self._config)
        else:
            self._ser = SocketWrapper(self._portspec, self._config)
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
        data = self._ser.read_frame_raw()
        if not data:
            return None
        self.last_active = time.time()
        try:
            frame = NXFrame.decode_line(data)
        except ReadFailure as e:
            LOG.error(str(e))
            return None
        return frame

    def _send(self, data):
        try:
            self._ser.write_frame_raw(data)
        except Exception:
            LOG.exception('Failed to send frame %r' % data)

    def send_ack(self):
        self._send([0x1D])

    def send_nack(self):
        self._send([0x1E])

    def get_zone_name(self, number):
        self._queue.append([0x23, number - 1])

    def get_zone_status(self, number):
        self._queue.append([0x24, number - 1])

    def arm_stay(self, partition):
        self._queue.append([0x3E, 0x00, partition])

    def arm_exit(self, partition):
        self._queue.append([0x3E, 0x02, partition])

    def arm_auto(self, partition):
        self._queue.append([0x3D, 0x05, 0x01, 0x01])

    def disarm(self, master_pin, partition):
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
        if self.zone_name_update:
            self._get_zone(number).name = name.strip()
            LOG.debug('Zone info from %s' % self.zones.keys())
            self._write_config()
        else:
            LOG.debug('Zone name not updating')

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
        euro_format = self._config.getboolean('config', 'euro_date_format',
                                              fallback=False)
        if euro_format:
            month = frame.data[6]
            day = frame.data[5]
        else:
            month = frame.data[5]
            day = frame.data[6]

        hour = frame.data[7]
        minute = frame.data[8]
        now = datetime.datetime.now()
        if month > now.month:
            year = now.year - 1
        else:
            year = now.year
        try:
            event.timestamp = datetime.datetime(
                year=year, month=month, day=day,
                hour=hour, minute=minute)
        except ValueError:
            LOG.error('Log event had invalid date, or format needs to be set')
            return
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

    def generate_heartbeat_activity(self):
        self.get_system_status()

    def controller_loop(self):
        self.set_time()
        self.get_system_status()

        try:
            max_zone = self._config.getint('config', 'max_zone')
        except configparser.NoOptionError:
            max_zone = 8
            self._config.set('config', 'max_zone', str(max_zone))

        for i in range(1, max_zone + 1):
            self.get_zone_status(i)
            if not self._config.has_option('zones', str(i)):
                self.get_zone_name(i)

        watchdog = time.time()

        while self.running:
            frame = self.process_next()
            if frame is None:
                if time.time() - watchdog < self._idle_time_heartbeat_seconds:
                    self._run_queue()
                else:
                    # After time with no activity - generate
                    # something to make sure we are still alive
                    LOG.info('No activity for a while, heartbeating')
                    self.generate_heartbeat_activity()
                    watchdog = time.time()
                continue
            watchdog = time.time()
            LOG.debug('Received: %i %s (data %s)' % (frame.msgtype,
                                                     frame.type_name,
                                                     frame.data))
            if frame.ack_required:
                LOG.debug('Sending ACK')
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
            else:
                LOG.debug('Unsupported frame type %i (0x%02x)' % (
                    frame.msgtype, frame.msgtype))

    def controller_loop_safe(self):
        self.running = True

        while self.running:
            try:
                self.connect()
                self.controller_loop()
            except Exception as e:
                LOG.exception('Controller loop exited: %s' % e)
                LOG.warning('Waiting 10s before reconnecting...')
                time.sleep(10)
