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


class Zone(object):
    STATUS_FLAGS = [
        'Faulted', 'Trouble', 'Bypass', 'Inhibit', 'Low battery',
        'Loss of supervision', 'Reserved',]

    TYPE_FLAGS = [
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

    def __init__(self, number):
        self.number = number
        self.name = 'Unknown'
        self.state = None
        self.condition_flags = []
        self.type_flags = []

    @property
    def bypassed(self):
        return ('Inhibit' in self.condition_flags or
                'Bypass' in self.condition_flags)


class Partition(object):
    CONDITION_FLAGS = [
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

    def __init__(self, number):
        self.number = number
        self.condition_flags = []
        self.last_user = None

    @property
    def armed(self):
        return 'Armed' in self.condition_flags


class System(object):
    STATUS_FLAGS = [
        ['Line seizure', 'Off hook', 'Initial handshake received',
         'Download in progress', 'Dialer delay in progress',
         'Using backup phone', 'Listen in active', 'Two way lockout'],
        ['Ground fault', 'Phone fault', 'Fail to communicate',
         'Fuse fault', 'Box tamper', 'Siren tamper/trouble', 'Low battery',
         'AC fail'],
        ['Expander box tamper', 'Expander AC failure',
         'Expander low battery', 'Expander loss of supervision',
         'Expander auxiliary output over current',
         'Auxiliary communication channel failure',
         'Expander bell fault', 'Reserved'],
        ['6 digit PIN enabled', 'Programming token in use',
         'PIN required for local download', 'Global pulsing buzzer',
         'Global Siren on', 'Global steady siren',
         'Bus device has line seized',
         'Bus device has requested sniff mode'],
        ['Dynamic battery test', 'AC power on', 'Low battery memory',
         'Ground fault memory', 'Fire alarm verification being timed',
         'Smoke power reset', '50 Hz line power detected',
         'Timing a high voltage battery change'],
        ['Communication since last autotest', 'Power up delay in progress',
         'Walk test mode', 'Loss of system time', 'Enroll requested',
         'Test fixture mode', 'Control shutdown mode',
         'Timing a cancel window'],
        ['reserved', 'reserved', 'reserved', 'reserved', 'reserved',
         'reserved', 'reserved', 'Call back in progress'],
        ['Phone line faulted', 'Voltage present interrupt active',
         'House phone off hook', 'Phone line monitor enabled',
         'Sniffing', 'Last read was off hook', 'Listen in requested',
         'Listen in trigger'],
        ['Valid partition 1', 'Valid partition 2', 'Valid partition 3',
         'Valid partition 4', 'Valid partition 5', 'Valid partition 6',
         'Valid partition 7', 'Valid partition 8'],
    ]

    def __init__(self):
        self.panel_id = 0
        self.status_flags = []


class NX584Extension(object):
    def __init__(self, controller):
        self._controller = controller

    def zone_status(self, zone):
        pass

    def partition_status(self, partition):
        pass

    def device_command(self, house, unit, command):
        pass

    def system_status(self, system):
        pass
