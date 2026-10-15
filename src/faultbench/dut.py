"""The device under test. Implement Dut for your receiver; ReferenceDut is a plain-Python model of a
black-channel heartbeat receiver (authenticate, check sequence, time out) used by faultbench's own tests."""
from typing import Protocol

from .heartbeat import Frame, fnv1a_tag


class Dut(Protocol):
    def on_frame(self, data: bytes, now_ms: int) -> None: ...
    def step(self, now_ms: int) -> bool:
        """Advance the receiver to now_ms and return the machine-enable output."""
        ...


class ReferenceDut:
    """Enable goes high on a valid, fresh heartbeat and drops `timeout_ms` after the last one."""

    def __init__(self, key=0x1234, timeout_ms=300, tagger=fnv1a_tag):
        self.key = key
        self.timeout_ms = timeout_ms
        self.tagger = tagger
        self.last_valid_ms = None
        self.last_seq = None
        self.enable = False
        self.rejected = []

    def verify(self, f: Frame) -> bool:
        return self.tagger(self.key, f.seq, f.payload) == f.tag

    def on_frame(self, data: bytes, now_ms: int) -> None:
        try:
            f = Frame.decode(data)
        except ValueError:
            self.rejected.append(("malformed", now_ms)); return
        if not self.verify(f):
            self.rejected.append(("bad_tag", now_ms)); return
        if self.last_seq is not None and f.seq <= self.last_seq:
            self.rejected.append(("replay", now_ms)); return
        self.last_seq = f.seq
        self.last_valid_ms = now_ms
        self.enable = True

    def step(self, now_ms: int) -> bool:
        if self.last_valid_ms is None or now_ms - self.last_valid_ms >= self.timeout_ms:
            self.enable = False
        return self.enable
