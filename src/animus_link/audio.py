import audioop

import numpy as np


class RateConverter:
    def __init__(self, src_rate: int, dst_rate: int):
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self.state = None

    def convert(self, pcm: bytes) -> bytes:
        if self.src_rate == self.dst_rate:
            return pcm
        out, self.state = audioop.ratecv(
            pcm, 2, 1, self.src_rate, self.dst_rate, self.state
        )
        return out


def normalize_pcm_frame(pcm_bytes: bytes, frame_samples: int) -> bytes:
    target = frame_samples * 2
    return (pcm_bytes + b"\x00" * target)[:target]


def pcm_peak(pcm_bytes: bytes) -> int:
    if not pcm_bytes:
        return 0
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
    if pcm.size == 0:
        return 0
    return int(np.max(np.abs(pcm.astype(np.int32))))


def apply_gain(pcm_bytes: bytes, gain: float) -> bytes:
    if gain == 1.0 or not pcm_bytes:
        return pcm_bytes
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    pcm = np.clip(pcm * gain, -32768, 32767).astype(np.int16)
    return pcm.tobytes()
