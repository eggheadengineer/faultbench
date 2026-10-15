"""CAN fault injection with fault-tolerant-time-interval checks, on a virtual bus, under virtual time."""

__version__ = "0.1.0"

from .clock import VirtualClock
from .bus import CanLink
from .faults import Drop, Delay, CorruptTag, Replay, Stuck, Stop, FaultPlan
from .heartbeat import HeartbeatSource, Frame
from .dut import Dut, ReferenceDut
from .harness import Harness, FttiViolation

__all__ = ["VirtualClock", "CanLink", "Drop", "Delay", "CorruptTag", "Replay", "Stuck", "Stop", "FaultPlan",
           "HeartbeatSource", "Frame", "Dut", "ReferenceDut", "Harness", "FttiViolation"]
