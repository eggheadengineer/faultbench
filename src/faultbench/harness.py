"""Drives heartbeats over the virtual bus into the DUT under virtual time, applies the fault plan, records
the enable output over time, and checks the fault-tolerant time interval."""
from dataclasses import dataclass

from .bus import CanLink
from .clock import VirtualClock
from .faults import FaultPlan
from .heartbeat import HeartbeatSource


class FttiViolation(AssertionError):
    pass


@dataclass
class Sample:
    t_ms: int
    enable: bool


class Harness:
    def __init__(self, dut, source: HeartbeatSource | None = None, plan: FaultPlan | None = None,
                 link: CanLink | None = None, clock: VirtualClock | None = None, step_ms=10):
        self.dut = dut
        self.source = source or HeartbeatSource()
        self.plan = plan or FaultPlan()
        self.link = link or CanLink()
        self.clock = clock or VirtualClock()
        self.step_ms = step_ms
        self.timeline: list[Sample] = []
        self.delivered = 0
        self._pending = []          # (deliver_at_ms, data) for delayed frames
        self._next_tx_ms = 0
        self.wire_history = []      # frames actually transmitted, in order: what a replay attacker could have captured
        self._ctx = {"history": self.wire_history, "tagger": self.source.tagger, "key": self.source.key}

    # -- driving
    def _transmit_due(self):
        now = self.clock.now_ms
        while self._next_tx_ms <= now:
            frame = self.source.next_frame()
            fault = self.plan.active(self._next_tx_ms)
            data_frame, delay = (frame, 0) if fault is None else fault.apply(frame, self._next_tx_ms, self._ctx)
            if data_frame is not None:
                if delay:
                    self._pending.append((self._next_tx_ms + delay, data_frame.encode()))
                else:
                    self.link.send(data_frame.encode())
                if data_frame is frame:          # only genuine, unmodified frames are worth capturing
                    self.wire_history.append(frame)
            self._next_tx_ms += self.source.period_ms

    def _deliver(self):
        now = self.clock.now_ms
        ready = [p for p in self._pending if p[0] <= now]
        self._pending = [p for p in self._pending if p[0] > now]
        for _, data in sorted(ready):
            self.link.send(data)
        for data in self.link.drain():
            self.dut.on_frame(data, now)
            self.delivered += 1

    def run_until(self, t_ms):
        """Advance virtual time to t_ms in step_ms increments, sampling the enable output each step."""
        while self.clock.now_ms < t_ms:
            self._transmit_due()
            self._deliver()
            self.timeline.append(Sample(self.clock.now_ms, bool(self.dut.step(self.clock.now_ms))))
            self.clock.advance(self.step_ms)
        return self

    # -- queries
    def enable_at(self, t_ms):
        last = None
        for s in self.timeline:
            if s.t_ms <= t_ms:
                last = s.enable
        return last

    def first_disable_after(self, t_ms):
        """Time of the first sample at or after t_ms where enable is False, or None."""
        for s in self.timeline:
            if s.t_ms >= t_ms and not s.enable:
                return s.t_ms
        return None

    def ever_enabled_between(self, a_ms, b_ms):
        return any(s.enable for s in self.timeline if a_ms <= s.t_ms <= b_ms)

    # -- assertions
    def assert_safe_within(self, fault_at_ms, ftti_ms):
        """Enable must be False at some sample within [fault_at_ms, fault_at_ms + ftti_ms]."""
        self.run_until(max(self.clock.now_ms, fault_at_ms + ftti_ms + self.step_ms))
        t = self.first_disable_after(fault_at_ms)
        if t is None or t > fault_at_ms + ftti_ms:
            seen = "never" if t is None else f"at {t} ms ({t - fault_at_ms} ms after the fault)"
            raise FttiViolation(f"enable did not drop within FTTI {ftti_ms} ms of the fault at {fault_at_ms} ms: {seen}")
        return t - fault_at_ms

    def assert_stays_enabled(self, a_ms, b_ms):
        self.run_until(max(self.clock.now_ms, b_ms + self.step_ms))
        bad = [s.t_ms for s in self.timeline if a_ms <= s.t_ms <= b_ms and not s.enable]
        if bad:
            raise AssertionError(f"enable dropped at {bad[0]} ms inside [{a_ms}, {b_ms}] ms where it should have stayed up (nuisance trip)")

    def close(self):
        self.link.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
