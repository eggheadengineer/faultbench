# faultbench

CAN fault injection with fault-tolerant-time-interval checks, written as pytest tests on a virtual bus under
virtual time. Inject a dropped, delayed, corrupted, replayed, or stuck heartbeat into a receiver and prove it
reaches its safe state inside the FTTI, or prove it does not.

No hardware, no kernel module, no sleeps. A 300 ms timeout scenario runs in microseconds and gives the same
answer every time, so it belongs in CI next to the unit tests.

```
pip install "faultbench[dev] @ git+https://github.com/eggheadengineer/faultbench"
pytest --junitxml=results/junit.xml
```

## The idea

A black-channel safety link does not work by sending "stop". It works by continuously sending "all is well"
and stopping the machine when that stops arriving. So the questions that matter are:

- When the heartbeat stops, how long until the enable output drops? (deletion)
- Does a late heartbeat trip it, and should it? (delay)
- Is a forged or corrupted heartbeat rejected? (corruption, insertion)
- Does a replayed valid heartbeat keep the machine running? (repetition)
- How many consecutive lost frames are tolerated before a nuisance trip? (availability)

Those are the EN 50159 transmission threats, and each one is a fault in `faultbench.faults`.

## A scenario

```python
from faultbench import Harness, HeartbeatSource, FaultPlan, Stop, Drop, ReferenceDut

def test_link_loss_trips_within_ftti():
    """@verifies SSR-001"""
    with Harness(ReferenceDut(timeout_ms=300), HeartbeatSource(period_ms=100), FaultPlan(Stop(at_ms=1000))) as h:
        detect_ms = h.assert_safe_within(fault_at_ms=1000, ftti_ms=300)

def test_two_dropped_frames_do_not_trip():
    with Harness(ReferenceDut(), HeartbeatSource(period_ms=100), FaultPlan(Drop(at_ms=1000, count=2))) as h:
        h.assert_stays_enabled(100, 3000)
```

`assert_safe_within` fails with the measured detection time when the receiver is too slow:
`enable did not drop within FTTI 300 ms of the fault at 1000 ms: at 1600 ms (600 ms after the fault)`.

## Your receiver

Implement two methods and the harness drives it:

```python
class MyReceiver:
    def on_frame(self, data: bytes, now_ms: int) -> None: ...   # a CAN FD frame arrived
    def step(self, now_ms: int) -> bool: ...                    # advance to now_ms, return machine-enable
```

That can wrap real firmware through ctypes (the reqthread reference project does this with its C
supervisor), a simulator, or a serial link to a bench board as long as time is driven by the harness.

## Faults

| Fault | Threat | What it does |
| --- | --- | --- |
| `Stop(at_ms)` | deletion | transmitter goes silent for good |
| `Drop(at_ms, count)` | deletion | deletes the next `count` heartbeats |
| `Delay(at_ms, ms)` | delay | every heartbeat arrives `ms` late |
| `CorruptTag(at_ms, count)` | corruption / insertion | flips bits in the authentication tag |
| `Replay(at_ms, index)` | repetition | resends a previously valid frame instead of a fresh one |
| `Stuck(at_ms, value)` | stuck sensor | freezes the payload while seq and tag stay valid |

Frames are 12 bytes (u32 seq, 4-byte payload, u32 tag) over CAN FD on python-can's virtual interface. The
default tag is a keyed FNV-1a checksum standing in for a real MAC; pass your own `tagger` to match a device.

## With reqthread

The tests are ordinary pytest tests, so `--junitxml` output flows into
[reqthread](https://github.com/eggheadengineer/reqthread) and a `@verifies SSR-001` docstring traces the
scenario to the safety requirement it exercises, and through it to the hazard it mitigates.

## Tests

```
pip install -e ".[dev]" && pytest -v
```

Scenarios run against `ReferenceDut`, a plain-Python black-channel receiver. One test deliberately uses a
receiver without a sequence check to show the replay scenario catching it.

## License

Apache-2.0.
