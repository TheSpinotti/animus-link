from __future__ import annotations

import argparse
import asyncio
import logging
import os
import queue
import struct
import subprocess
import threading

import numpy as np
import sounddevice as sd
import websockets

from animus_link.audio import RateConverter, apply_gain, normalize_pcm_frame, pcm_peak
from animus_link.config import AppConfig, load_config
from animus_link.protocol import (
    CTRL_START,
    MT_AUDIO,
    MT_CONTROL,
    MT_HANDSHAKE,
    MT_PING,
    make_msg,
)
from animus_link.windows_audio import find_sd_device, force_personaplex_input

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("animus_link.bridge")

_stats = {
    "sent": 0,
    "recv": 0,
    "out_peak": 0,
    "in_peak": 0,
    "cable_peak": 0,
    "cable_out_peak": 0,
}



def build_personaplex_args(config: AppConfig) -> list[str]:
    return [
        "-r", ".",
        "-v", config.personaplex.voice,
        "-c", str(config.personaplex.context),
        "-p", config.personaplex.prompt,
    ]


class Bridge:
    def __init__(self, config: AppConfig, shutdown_event: asyncio.Event):
        self.config = config
        self.clients: set = set()
        self._lock = threading.Lock()
        self._shutdown_event = shutdown_event
        self._personaplex_args = build_personaplex_args(config)

        pp_idx, pp_rate = find_sd_device(config.windows_audio.personaplex_capture_name, input=True)
        log.info("PersonaPlex capture: [%s] @ %s Hz", pp_idx, pp_rate)

        ci_idx, ci_rate = find_sd_device(config.windows_audio.cable_input_name, input=False)
        log.info("CABLE Input: [%s] @ %s Hz", ci_idx, ci_rate)
        self._ci_idx = ci_idx
        self._ci_rate = ci_rate

        co_idx, co_rate = find_sd_device(config.windows_audio.cable_output_name, input=True)
        log.info("CABLE Output monitor: [%s] @ %s Hz", co_idx, co_rate)
        self._co_idx = co_idx
        self._co_rate = co_rate

        self._pp_idx = pp_idx
        self._pp_rate = pp_rate
        self._pp_to_wire = RateConverter(self._pp_rate, config.audio.sample_rate)
        self._wire_to_ci = RateConverter(config.audio.sample_rate, self._ci_rate)

        self._write_q: queue.Queue = queue.Queue(maxsize=8)
        self._out_q: asyncio.Queue | None = None
        self._stream = None
        self._cable_monitor_stream = None
        self._personaplex: subprocess.Popen | None = None

        threading.Thread(target=self._cable_write_loop, daemon=True).start()

    def launch_personaplex(self):
        if self._personaplex and self._personaplex.poll() is None:
            return
        force_personaplex_input(
            self.config.runtime.soundvolumeview_exe,
            self.config.windows_audio.cable_capture_id,
            self.config.windows_audio.cable_capture_names,
            self.config.windows_audio.personaplex_output_name,
        )
        personaplex_exe = os.path.join(self.config.runtime.personaplex_dir, "personaplex.exe")
        log.info("Launching PersonaPlex...")
        self._personaplex = subprocess.Popen(
            [personaplex_exe] + self._personaplex_args,
            cwd=self.config.runtime.personaplex_dir,
        )
        log.info("PersonaPlex PID: %s", self._personaplex.pid)

    def stop_personaplex(self):
        if self._personaplex and self._personaplex.poll() is None:
            log.info("Terminating PersonaPlex...")
            self._personaplex.terminate()
            try:
                self._personaplex.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._personaplex.kill()

    def start_audio(self, loop: asyncio.AbstractEventLoop):
        self._out_q = asyncio.Queue(maxsize=60)
        audio = self.config.audio

        def cable_monitor_callback(indata, frames, time_info, status):
            try:
                pcm = indata[:, 0].astype(np.int16).tobytes()
                _stats["cable_out_peak"] = max(_stats["cable_out_peak"], pcm_peak(pcm))
            except Exception as e:
                log.warning("CABLE Output monitor callback: %s", e)

        def capture_callback(indata, frames, time_info, status):
            try:
                pcm_hw = indata[:, 0].astype(np.int16).tobytes()
                pcm = self._pp_to_wire.convert(pcm_hw)
                pcm = apply_gain(pcm, audio.output_gain)
                pcm = normalize_pcm_frame(pcm, audio.frame_samples)
                _stats["out_peak"] = max(_stats["out_peak"], pcm_peak(pcm))
                loop.call_soon_threadsafe(self._enqueue_out, make_msg(MT_AUDIO, pcm))
            except Exception as e:
                log.warning("capture callback: %s", e)

        frame_size = int(self._pp_rate * audio.frame_ms / 1000)
        self._stream = sd.InputStream(
            device=self._pp_idx,
            samplerate=self._pp_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_size,
            callback=capture_callback,
        )
        self._stream.start()

        cable_frame_size = int(self._co_rate * audio.frame_ms / 1000)
        self._cable_monitor_stream = sd.InputStream(
            device=self._co_idx,
            samplerate=self._co_rate,
            channels=1,
            dtype="int16",
            blocksize=cable_frame_size,
            callback=cable_monitor_callback,
        )
        self._cable_monitor_stream.start()
        log.info("Bridge audio started")

    def _enqueue_out(self, msg: bytes):
        if self._out_q.qsize() < 50:
            self._out_q.put_nowait(msg)

    async def sender_task(self):
        while True:
            msg = await self._out_q.get()
            with self._lock:
                clients = list(self.clients)
            if clients:
                _stats["sent"] += 1
                await asyncio.gather(
                    *(self._safe_send(ws, msg) for ws in clients),
                    return_exceptions=True,
                )

    async def _safe_send(self, ws, msg: bytes):
        try:
            await ws.send(msg)
        except Exception:
            pass

    def enqueue_pcm(self, pcm_24k: bytes):
        audio = self.config.audio
        _stats["in_peak"] = max(_stats["in_peak"], pcm_peak(pcm_24k))
        pcm_24k = apply_gain(pcm_24k, audio.input_gain)
        if self._ci_rate != audio.sample_rate:
            pcm_24k = self._wire_to_ci.convert(pcm_24k)
        frame_bytes = int(self._ci_rate * audio.frame_ms / 1000) * 2

        if self._write_q.qsize() >= 6:
            while not self._write_q.empty():
                try:
                    self._write_q.get_nowait()
                except queue.Empty:
                    break

        for i in range(0, len(pcm_24k), frame_bytes):
            chunk = pcm_24k[i : i + frame_bytes]
            if len(chunk) < frame_bytes:
                chunk += b"\x00" * (frame_bytes - len(chunk))
            _stats["cable_peak"] = max(_stats["cable_peak"], pcm_peak(chunk))
            try:
                self._write_q.put_nowait(chunk)
                _stats["recv"] += 1
            except queue.Full:
                pass

    def _cable_write_loop(self):
        frame_samples = int(self._ci_rate * self.config.audio.frame_ms / 1000)
        silence = np.zeros(frame_samples, dtype=np.int16)
        with sd.OutputStream(
            device=self._ci_idx,
            samplerate=self._ci_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
        ) as stream:
            while True:
                try:
                    chunk = self._write_q.get(timeout=0.05)
                    audio = np.frombuffer(chunk, dtype=np.int16)
                except queue.Empty:
                    audio = silence
                try:
                    stream.write(audio)
                except Exception as e:
                    log.warning("CABLE write: %s", e)

    def add_client(self, ws):
        with self._lock:
            self.clients.add(ws)
        self.launch_personaplex()

    def remove_client(self, ws):
        with self._lock:
            self.clients.discard(ws)
            has_clients = bool(self.clients)
        if not has_clients:
            log.info("Last client disconnected; shutting down bridge.")
            self._shutdown_event.set()

    def stop(self):
        if self._stream:
            self._stream.stop()
        if self._cable_monitor_stream:
            self._cable_monitor_stream.stop()
        self.stop_personaplex()


bridge: Bridge | None = None


async def stats_printer():
    while True:
        await asyncio.sleep(5)
        log.info(
            "[audio] sent=%s out_peak=%s | recv=%s in_peak=%s cable_peak=%s cable_out_peak=%s",
            _stats["sent"],
            _stats["out_peak"],
            _stats["recv"],
            _stats["in_peak"],
            _stats["cable_peak"],
            _stats["cable_out_peak"],
        )
        for key in _stats:
            _stats[key] = 0


async def handler(websocket):
    remote = websocket.remote_address
    log.info("Client connected: %s", remote)
    bridge.add_client(websocket)
    await websocket.send(make_msg(MT_HANDSHAKE, struct.pack("<II", 0, 0)))
    await websocket.send(make_msg(MT_CONTROL, bytes([CTRL_START])))
    try:
        async for raw in websocket:
            if not isinstance(raw, bytes) or not raw:
                continue
            mt, payload = raw[0], raw[1:]
            if mt == MT_AUDIO and payload:
                bridge.enqueue_pcm(normalize_pcm_frame(payload, bridge.config.audio.frame_samples))
            elif mt == MT_PING:
                await websocket.send(make_msg(MT_PING))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        bridge.remove_client(websocket)
        log.info("Client disconnected: %s", remote)


async def run_bridge(config: AppConfig):
    global bridge
    shutdown_event = asyncio.Event()
    bridge = Bridge(config, shutdown_event=shutdown_event)
    loop = asyncio.get_running_loop()
    bridge.start_audio(loop)
    host = config.network.bridge_host
    port = config.network.bridge_port
    log.info("Listening on ws://%s:%s", host, port)

    sender = asyncio.create_task(bridge.sender_task())
    stats = asyncio.create_task(stats_printer())
    try:
        async with websockets.serve(handler, host, port):
            await shutdown_event.wait()
    finally:
        sender.cancel()
        stats.cancel()
        await asyncio.gather(sender, stats, return_exceptions=True)
        if bridge:
            bridge.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animus Link bridge")
    parser.add_argument("--config", default="config.toml", help="Path to config TOML")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    try:
        asyncio.run(run_bridge(config))
    except KeyboardInterrupt:
        log.info("Shutting down...")
        if bridge:
            bridge.stop()


if __name__ == "__main__":
    main()
