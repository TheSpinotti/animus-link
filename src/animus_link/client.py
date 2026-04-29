from __future__ import annotations

import argparse
import asyncio
import logging
import queue
import urllib.request

import numpy as np
import sounddevice as sd
import websockets

from animus_link.audio import RateConverter, apply_gain, normalize_pcm_frame, pcm_peak
from animus_link.config import load_config
from animus_link.protocol import MT_AUDIO, MT_CONTROL, MT_HANDSHAKE, MT_PING, make_msg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("animus_link.client")


async def start_remote_bridge(server: str, launcher_port: int):
    url = f"http://{server}:{launcher_port}/start"
    log.info("Bridge not reachable; asking launcher to start it: %s", url)

    def request_start():
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read().decode("utf-8", errors="replace").strip()

    text = await asyncio.to_thread(request_start)
    log.info("Launcher response: %s", text)


async def connect_ws(uri: str):
    return await websockets.connect(uri, max_size=2**20, open_timeout=5)


async def run_client(
    server: str,
    config_path: str,
    playback: bool = True,
    no_remote_start: bool = False,
):
    config = load_config(config_path)
    audio = config.audio
    uri = f"ws://{server}:{config.network.bridge_port}"

    in_info = sd.query_devices(kind="input")
    out_info = sd.query_devices(kind="output")
    in_rate = int(in_info["default_samplerate"])
    out_rate = int(out_info["default_samplerate"])
    log.info("Mic: %r @ %s Hz", in_info["name"], in_rate)
    log.info("Speakers: %r @ %s Hz", out_info["name"], out_rate)
    if not playback:
        log.info("Playback disabled; receiving server audio but not writing to speakers.")

    play_q: queue.Queue = queue.Queue(maxsize=audio.client_play_max_queue_frames)
    send_q: asyncio.Queue = asyncio.Queue(maxsize=60)
    loop = asyncio.get_running_loop()

    in_block = int(in_rate * audio.frame_ms / 1000)
    out_block = int(out_rate * audio.frame_ms / 1000)
    silence = np.zeros(out_block, dtype=np.int16)
    mic_buf = np.zeros(0, dtype=np.int16)
    mic_to_wire = RateConverter(in_rate, audio.sample_rate)
    wire_to_out = RateConverter(audio.sample_rate, out_rate)
    playback_ready = False
    stats = {"mic_peak": 0, "play_peak": 0, "underflows": 0, "drops": 0}

    def _enqueue_send(msg: bytes):
        if send_q.qsize() < 55:
            send_q.put_nowait(msg)

    def mic_callback(indata, frames, time_info, status):
        nonlocal mic_buf
        pcm = indata[:, 0].astype(np.int16)
        if in_rate != audio.sample_rate:
            raw = mic_to_wire.convert(pcm.tobytes())
            pcm = np.frombuffer(raw, dtype=np.int16)
        mic_buf = np.concatenate([mic_buf, pcm])
        while len(mic_buf) >= audio.frame_samples:
            chunk = mic_buf[: audio.frame_samples].tobytes()
            mic_buf = mic_buf[audio.frame_samples :]
            chunk = apply_gain(chunk, audio.client_mic_gain)
            stats["mic_peak"] = max(stats["mic_peak"], pcm_peak(chunk))
            loop.call_soon_threadsafe(_enqueue_send, make_msg(MT_AUDIO, chunk))

    def play_callback(outdata, frames, time_info, status):
        nonlocal playback_ready
        if not playback:
            outdata[:, 0] = silence[:frames]
            return
        if not playback_ready:
            if play_q.qsize() < audio.client_play_prebuffer_frames:
                outdata[:, 0] = silence[:frames]
                return
            playback_ready = True
        try:
            chunk = play_q.get_nowait()
            samples = np.frombuffer(chunk, dtype=np.int16)
        except queue.Empty:
            playback_ready = False
            stats["underflows"] += 1
            samples = silence
        if len(samples) < frames:
            samples = np.pad(samples, (0, frames - len(samples)))
        outdata[:, 0] = samples[:frames]

    try:
        ws = await connect_ws(uri)
    except (TimeoutError, OSError):
        if no_remote_start:
            raise
        await start_remote_bridge(server, config.network.launcher_port)
        await asyncio.sleep(2)
        ws = await connect_ws(uri)

    try:
        log.info("Connected to %s", uri)

        async def sender():
            while True:
                msg = await send_q.get()
                try:
                    await ws.send(msg)
                except Exception:
                    break

        async def receiver():
            frame_bytes = out_block * 2
            async for raw in ws:
                if not isinstance(raw, bytes) or not raw:
                    continue
                mt, payload = raw[0], raw[1:]
                if mt == MT_AUDIO:
                    if not payload:
                        continue
                    pcm_24k = normalize_pcm_frame(payload, audio.frame_samples)
                    pcm_24k = apply_gain(pcm_24k, audio.client_play_gain)
                    stats["play_peak"] = max(stats["play_peak"], pcm_peak(pcm_24k))
                    if out_rate != audio.sample_rate:
                        pcm_24k = wire_to_out.convert(pcm_24k)
                    if play_q.qsize() >= audio.client_play_max_queue_frames - 2:
                        while play_q.qsize() > audio.client_play_prebuffer_frames:
                            try:
                                play_q.get_nowait()
                                stats["drops"] += 1
                            except queue.Empty:
                                break
                    for i in range(0, len(pcm_24k), frame_bytes):
                        chunk = pcm_24k[i : i + frame_bytes]
                        if len(chunk) < frame_bytes:
                            chunk += b"\x00" * (frame_bytes - len(chunk))
                        try:
                            play_q.put_nowait(chunk)
                        except queue.Full:
                            pass
                elif mt == MT_PING:
                    await ws.send(make_msg(MT_PING))
                elif mt == MT_HANDSHAKE:
                    log.info("Handshake OK")
                elif mt == MT_CONTROL:
                    log.info("Control: %s", payload.hex())

        async def stats_printer():
            while True:
                await asyncio.sleep(5)
                log.info(
                    "[audio] mic_peak=%s play_peak=%s underflows=%s drops=%s send_q=%s play_q=%s",
                    stats["mic_peak"],
                    stats["play_peak"],
                    stats["underflows"],
                    stats["drops"],
                    send_q.qsize(),
                    play_q.qsize(),
                )
                stats["mic_peak"] = stats["play_peak"] = 0
                stats["underflows"] = stats["drops"] = 0

        with sd.InputStream(
            samplerate=in_rate,
            channels=1,
            dtype="int16",
            blocksize=in_block,
            callback=mic_callback,
        ):
            with sd.OutputStream(
                samplerate=out_rate,
                channels=1,
                dtype="int16",
                blocksize=out_block,
                callback=play_callback,
            ):
                log.info("Streaming. Press Ctrl+C to quit.")
                await asyncio.gather(sender(), receiver(), stats_printer())
    finally:
        await ws.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animus Link client")
    parser.add_argument("server", help="Server IP or Tailscale hostname")
    parser.add_argument("--config", default="config.toml", help="Path to config TOML")
    parser.add_argument(
        "--no-playback",
        action="store_true",
        help="Do not play server audio; useful for diagnosing local mic monitoring.",
    )
    parser.add_argument(
        "--no-remote-start",
        action="store_true",
        help="Only connect to an already-running bridge; do not contact the launcher.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        asyncio.run(
            run_client(
                args.server,
                args.config,
                playback=not args.no_playback,
                no_remote_start=args.no_remote_start,
            )
        )
    except KeyboardInterrupt:
        log.info("Bye.")


if __name__ == "__main__":
    main()
