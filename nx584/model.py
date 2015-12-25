class Zone(object):
    def __init__(self, number):
        self.number = number
        self.name = 'Unknown'
        self.state = None
        self.condition_flags = []
        self.type_flags = []


class Partition(object):
    def __init__(self, number):
        self.number = number
        self.condition_flags = []
        self.last_user = None
