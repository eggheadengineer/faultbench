"""The heartbeat the transmitter sends: a sequence number, a payload, and an authentication tag.

The default tag is a keyed FNV-1a checksum. It is NOT cryptographic; it stands in for a real MAC so the
harness can build valid and forged frames without a crypto dependency. Supply your own `tagger` to match
a real device."""
import struct
from dataclasses import dataclass

PAYLOAD_LEN = 4


def fnv1a_tag(key: int, seq: int, payload: bytes) -> int:
    h = (key ^ 0x811C9DC5) & 0xFFFFFFFF
    for b in struct.pack("<I", seq) + payload:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


@dataclass(frozen=True)
class Frame:
    seq: int
    payload: bytes
    tag: int

    def encode(self) -> bytes:
        return struct.pack("<I", self.seq) + self.payload + struct.pack("<I", self.tag)

    @classmethod
    def decode(cls, data: bytes):
        if len(data) != 4 + PAYLOAD_LEN + 4:
            raise ValueError(f"frame must be {4 + PAYLOAD_LEN + 4} bytes, got {len(data)}")
        seq = struct.unpack_from("<I", data, 0)[0]
        payload = data[4:4 + PAYLOAD_LEN]
        tag = struct.unpack_from("<I", data, 4 + PAYLOAD_LEN)[0]
        return cls(seq, payload, tag)


class HeartbeatSource:
    """Generates the next valid heartbeat frame on demand. The harness decides when (and whether) it is sent."""

    def __init__(self, key=0x1234, period_ms=100, payload=b"\x01\x02\x03\x04", tagger=fnv1a_tag, first_seq=1):
        self.key = key
        self.period_ms = period_ms
        self.payload = payload
        self.tagger = tagger
        self.next_seq = first_seq
        self.history = []

    def next_frame(self) -> Frame:
        f = Frame(self.next_seq, self.payload, self.tagger(self.key, self.next_seq, self.payload))
        self.next_seq += 1
        self.history.append(f)
        return f
