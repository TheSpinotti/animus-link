from __future__ import annotations

import logging
import os
import subprocess
import tempfile

import sounddevice as sd

log = logging.getLogger("animus_link.windows_audio")


def _soundvolumeview_rows(soundvolumeview_exe: str) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    os.unlink(path)
    try:
        result = subprocess.run(
            [soundvolumeview_exe, "/scomma", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SoundVolumeView /scomma returned {result.returncode}")
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read().splitlines()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def find_sd_device(
    name_frag: str,
    input: bool,
    hostapi_name: str | None = None,
) -> tuple[int, int]:
    key = "max_input_channels" if input else "max_output_channels"
    hostapis = sd.query_hostapis()
    for i, device in enumerate(sd.query_devices()):
        if name_frag.lower() not in device["name"].lower() or device[key] <= 0:
            continue
        if hostapi_name is not None:
            hostapi = hostapis[int(device["hostapi"])]["name"]
            if hostapi_name.lower() not in hostapi.lower():
                continue
            return i, int(device["default_samplerate"])
        return i, int(device["default_samplerate"])
    if hostapi_name is not None:
        raise RuntimeError(f"Device not found: {name_frag!r} on host API {hostapi_name!r}")
    raise RuntimeError(f"Device not found: {name_frag!r}")


def find_pyaudio_device(name: str, input: bool = True) -> tuple[int, int, int]:
    import pyaudiowpatch as pyaudio

    key = "maxInputChannels" if input else "maxOutputChannels"
    pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            device = pa.get_device_info_by_index(i)
            if name.lower() in device["name"].lower() and device[key] > 0:
                return (
                    i,
                    int(device["defaultSampleRate"]),
                    int(device[key]),
                )
    finally:
        pa.terminate()
    raise RuntimeError(f"PyAudio device not found: {name!r}")


def force_personaplex_audio_route(
    soundvolumeview_exe: str,
    personaplex_input_capture_id: str,
    personaplex_input_capture_names: list[str],
    personaplex_return_render_id: str,
    process: str = "personaplex.exe",
) -> None:
    if not os.path.exists(soundvolumeview_exe):
        raise RuntimeError(
            f"SoundVolumeView not found at {soundvolumeview_exe!r}; "
            "cannot configure PersonaPlex audio routing."
        )

    rows = _soundvolumeview_rows(soundvolumeview_exe)
    if not any(personaplex_input_capture_id.lower() in row.lower() for row in rows):
        raise RuntimeError(
            "PersonaPlex input bus is not visible to Windows audio routing: "
            f"{personaplex_input_capture_id!r}"
        )
    if not any(personaplex_return_render_id.lower() in row.lower() for row in rows):
        raise RuntimeError(
            "PersonaPlex return bus is not visible to Windows audio routing: "
            f"{personaplex_return_render_id!r}. Install/enable the dedicated "
            "return virtual cable before starting the bridge."
        )

    def run_svv(*args: str) -> bool:
        try:
            result = subprocess.run(
                [soundvolumeview_exe, *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except Exception as e:
            log.warning("SoundVolumeView %s raised: %s", args, e)
            return False
        if result.returncode != 0:
            log.warning("SoundVolumeView %s returned %s", args, result.returncode)
            return False
        return True

    run_svv("/SetDefault", personaplex_input_capture_id, "all")
    for role in ("0", "1", "2"):
        run_svv("/SetAppDefault", personaplex_input_capture_id, role, process)
        run_svv("/SetAppDefault", personaplex_return_render_id, role, process)

    # If "Listen to this device" stays enabled on CABLE Output, the client's mic
    # audio loops back through the default output and the loopback captures it,
    # arriving at the client as static underneath PersonaPlex's voice.
    listen_disabled = any(
        run_svv("/SetListenToThisDevice", name, "0")
        for name in personaplex_input_capture_names
    )
    if not listen_disabled:
        log.warning(
            "Failed to disable 'Listen to this device' on CABLE Output — static may occur."
        )

    log.info(
        "Forced PersonaPlex audio route for %s: input=%s output=%s",
        process,
        personaplex_input_capture_id,
        personaplex_return_render_id,
    )
