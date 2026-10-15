"""Faults the harness can inject into the heartbeat stream. Each maps to a transmission threat from
EN 50159 / the black-channel model: deletion, delay, corruption, repetition, insertion."""
import struct
from dataclasses import dataclass, field

from .heartbeat import Frame


@dataclass
class Fault:
    at_ms: int

    def apply(self, frame, now_ms, ctx):
        """Return (frame_or_None_to_send, delay_ms). ctx is the harness's mutable fault context."""
        return frame, 0


@dataclass
class Drop(Fault):
    """Delete the next `count` heartbeats after at_ms (deletion). count=None drops forever."""
    count: int | None = 1
    _left: int | None = field(default=None, init=False)

    def apply(self, frame, now_ms, ctx):
        if self._left is None:
            self._left = self.count
        if self._left is None:
            return None, 0
        if self._left > 0:
            self._left -= 1
            return None, 0
        return frame, 0


@dataclass
class Stop(Fault):
    """The transmitter goes silent at at_ms and never comes back (link loss, dead battery)."""

    def apply(self, frame, now_ms, ctx):
        return None, 0


@dataclass
class Delay(Fault):
    """Each heartbeat after at_ms arrives `ms` late (delay)."""
    ms: int = 0

    def apply(self, frame, now_ms, ctx):
        return frame, self.ms


@dataclass
class CorruptTag(Fault):
    """Flip bits in the authentication tag (corruption, or a forged frame): the receiver must reject it."""
    count: int | None = None
    _left: int | None = field(default=None, init=False)

    def apply(self, frame, now_ms, ctx):
        if self._left is None:
            self._left = self.count
        if self._left is not None:
            if self._left == 0:
                return frame, 0
            self._left -= 1
        return Frame(frame.seq, frame.payload, frame.tag ^ 0x5A5A5A5A), 0


@dataclass
class Replay(Fault):
    """Instead of fresh heartbeats, resend a previously valid frame (repetition / replay attack)."""
    index: int = -1          # which captured frame to replay; -1 = the most recent one that was on the wire

    def apply(self, frame, now_ms, ctx):
        captured = ctx["history"]        # frames that actually went over the wire before this one
        if not captured:
            return frame, 0
        return captured[self.index], 0


@dataclass
class Stuck(Fault):
    """The payload freezes at a fixed value while seq and tag stay valid (a stuck sensor the receiver may
    legitimately accept; useful for testing payload plausibility checks)."""
    value: bytes = b"\x00\x00\x00\x00"

    def apply(self, frame, now_ms, ctx):
        tagger, key = ctx["tagger"], ctx["key"]
        return Frame(frame.seq, self.value, tagger(key, frame.seq, self.value)), 0


class FaultPlan:
    """Ordered faults; the latest one whose at_ms has passed is active."""

    def __init__(self, *faults):
        self.faults = sorted(faults, key=lambda f: f.at_ms)

    def active(self, now_ms):
        act = None
        for f in self.faults:
            if f.at_ms <= now_ms:
                act = f
        return act
