import threading


class Event(object):
    def __init__(self, number, payload):
        self.number = number
        self.payload = payload

    def __repr__(self):
        return 'Event<%i>' % self.number


class EventQueue(object):
    def __init__(self, length, start=0):
        self._queue = []
        self._queue_lock = threading.Lock()
        self._length = length
        self._index = start
        self._condition = threading.Condition()
        self._min = start
        self._max = start

    def push(self, thing):
        self._condition.acquire()
        self._max += 1
        self._queue.append(Event(self._max, thing))
        self._queue = self._queue[0 - self._length:]
        self._min = self._queue[0].number
        self._condition.notify_all()
        self._condition.release()

    @property
    def current(self):
        return self._max

    def get(self, index, timeout=None):
        self._condition.acquire()

        data_available = lambda: index < self._min or self._max > index

        if not data_available():
            self._condition.wait(timeout)
        the_index = index - self._min + 1
        if the_index < 0:
            the_index = 0
        if data_available():
            result = self._queue[the_index:]
        else:
            result = None
        self._condition.release()
        return result
