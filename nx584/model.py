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
    def __init__(self, number):
        self.number = number
        self.condition_flags = []
        self.last_user = None

    @property
    def armed(self):
        return 'Armed' in self.condition_flags


class System(object):
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
