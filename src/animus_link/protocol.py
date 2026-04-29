SAMPLE_RATE = 24000
FRAME_MS = 40
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000

MT_HANDSHAKE = 0
MT_AUDIO = 1
MT_CONTROL = 3
MT_PING = 6

CTRL_START = 0


def make_msg(message_type: int, payload: bytes = b"") -> bytes:
    return bytes([message_type]) + payload
