"""faultbench's own scenarios against the reference receiver. Each test is also the template for a real DUT."""
import pytest

from faultbench import (CorruptTag, Delay, Drop, FaultPlan, Frame, FttiViolation, Harness, HeartbeatSource,
                        ReferenceDut, Replay, Stop, Stuck)

FTTI = 300          # the receiver's heartbeat timeout
PERIOD = 100        # 10 Hz heartbeat


def harness(*faults, timeout_ms=FTTI, step_ms=10):
    return Harness(ReferenceDut(timeout_ms=timeout_ms), HeartbeatSource(period_ms=PERIOD), FaultPlan(*faults), step_ms=step_ms)


class TestNominal:
    def test_enable_comes_up_and_stays_up(self):
        with harness() as h:
            h.assert_stays_enabled(PERIOD, 3000)
            assert h.delivered >= 29

    def test_nothing_delivered_means_never_enabled(self):
        with harness(Stop(at_ms=0)) as h:
            h.run_until(1000)
            assert not h.ever_enabled_between(0, 1000)


class TestDeletion:
    def test_link_loss_trips_within_ftti(self):
        with harness(Stop(at_ms=1000)) as h:
            detect = h.assert_safe_within(1000, FTTI)
            assert 200 <= detect <= FTTI   # last good frame at 900 ms -> timeout at 1200 ms -> 300 ms after 900

    def test_two_dropped_frames_do_not_trip(self):
        """Availability: the timeout tolerates two consecutive lost heartbeats at 10 Hz."""
        with harness(Drop(at_ms=1000, count=2)) as h:
            h.assert_stays_enabled(PERIOD, 3000)

    def test_three_dropped_frames_trip(self):
        with harness(Drop(at_ms=1000, count=3)) as h:
            h.assert_safe_within(1000, FTTI)

    def test_ftti_violation_is_reported_with_timing(self):
        """A receiver whose timeout is longer than the FTTI must fail the check, and say by how much."""
        with harness(Stop(at_ms=1000), timeout_ms=600) as h:
            with pytest.raises(FttiViolation, match="did not drop within FTTI 300 ms"):
                h.assert_safe_within(1000, FTTI)


class TestDelay:
    def test_delay_inside_ftti_is_tolerated(self):
        with harness(Delay(at_ms=1000, ms=150)) as h:
            h.assert_stays_enabled(PERIOD, 3000)

    def test_delay_beyond_ftti_trips(self):
        with harness(Delay(at_ms=1000, ms=400)) as h:
            h.assert_safe_within(1000, FTTI + 100)


class TestCorruption:
    def test_forged_tag_is_rejected_and_link_trips(self):
        with harness(CorruptTag(at_ms=1000)) as h:
            h.assert_safe_within(1000, FTTI)
            assert any(kind == "bad_tag" for kind, _ in h.dut.rejected)

    def test_single_corrupted_frame_does_not_trip(self):
        with harness(CorruptTag(at_ms=1000, count=1)) as h:
            h.assert_stays_enabled(PERIOD, 3000)


class TestRepetition:
    def test_replayed_frame_does_not_extend_enable(self):
        with harness(Replay(at_ms=1000)) as h:
            h.assert_safe_within(1000, FTTI)
            assert any(kind == "replay" for kind, _ in h.dut.rejected)

    def test_a_receiver_without_sequence_check_is_caught(self):
        """The whole reason for the sequence number: a replayable receiver stays enabled on stale frames."""
        class NoSeqCheck(ReferenceDut):
            def on_frame(self, data, now_ms):
                f = Frame.decode(data)
                if self.verify(f):
                    self.last_valid_ms = now_ms; self.enable = True
        h = Harness(NoSeqCheck(), HeartbeatSource(period_ms=PERIOD), FaultPlan(Replay(at_ms=1000)))
        with h, pytest.raises(FttiViolation):
            h.assert_safe_within(1000, FTTI)


class TestStuck:
    def test_stuck_payload_with_valid_seq_is_accepted(self):
        """Documents a limitation: a frozen payload with fresh seq/tag is indistinguishable from a healthy
        link at this layer. Plausibility checks on the payload belong to the application."""
        with harness(Stuck(at_ms=1000, value=b"\xff\xff\xff\xff")) as h:
            h.assert_stays_enabled(PERIOD, 3000)


class TestFrame:
    def test_roundtrip_and_size(self):
        f = Frame(7, b"\x01\x02\x03\x04", 0xDEADBEEF)
        data = f.encode()
        assert len(data) == 12
        assert Frame.decode(data) == f

    def test_bad_length_rejected(self):
        with pytest.raises(ValueError):
            Frame.decode(b"\x00" * 8)
