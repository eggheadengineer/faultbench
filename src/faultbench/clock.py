"""Virtual time. Nothing in faultbench sleeps; the harness advances the clock, so a 300 ms timeout test
runs in microseconds and gives the same answer every time."""


class VirtualClock:
    def __init__(self, start_ms=0):
        self._now = int(start_ms)

    @property
    def now_ms(self):
        return self._now

    def advance(self, ms):
        if ms < 0:
            raise ValueError("time only moves forward")
        self._now += int(ms)
        return self._now
