"""A transmitter/receiver pair on a python-can virtual bus. CAN FD, because safety frames with a sequence
number, payload and authentication tag do not fit in classic CAN's 8 bytes."""
import itertools

import can

_channels = itertools.count()


class CanLink:
    """Two ends of one virtual channel. Frames sent on `tx` arrive on `rx` immediately; the harness decides when
    the receiver looks."""

    def __init__(self, arbitration_id=0x100, channel=None):
        self.channel = channel or f"faultbench-{next(_channels)}"
        self.arbitration_id = arbitration_id
        self.tx = can.Bus(interface="virtual", channel=self.channel, receive_own_messages=False)
        self.rx = can.Bus(interface="virtual", channel=self.channel, receive_own_messages=False)
        self.sent = 0

    def send(self, data: bytes, arbitration_id=None):
        msg = can.Message(arbitration_id=arbitration_id or self.arbitration_id, data=data, is_fd=True,
                          is_extended_id=False)
        self.tx.send(msg)
        self.sent += 1

    def drain(self):
        """All frames waiting at the receiver, in order."""
        out = []
        while True:
            m = self.rx.recv(timeout=0)
            if m is None:
                return out
            out.append(bytes(m.data))

    def close(self):
        self.tx.shutdown()
        self.rx.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
