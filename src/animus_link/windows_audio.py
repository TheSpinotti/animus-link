from __future__ import annotations

import logging
import os
import subprocess

import sounddevice as sd

log = logging.getLogger("animus_link.windows_audio")


def find_sd_device(name_frag: str, input: bool) -> tuple[int, int]:
    key = "max_input_channels" if input else "max_output_channels"
    for i, device in enumerate(sd.query_devices()):
        if name_frag.lower() in device["name"].lower() and device[key] > 0:
            return i, int(device["default_samplerate"])
    raise RuntimeError(f"Device not found: {name_frag!r}")


def force_personaplex_input(
    soundvolumeview_exe: str,
    cable_capture_id: str,
    cable_capture_names: list[str],
) -> None:
    if not os.path.exists(soundvolumeview_exe):
        log.warning("SoundVolumeView not found; cannot force PersonaPlex input")
        return

    commands = [
        [soundvolumeview_exe, "/SetDefault", cable_capture_id, "all"],
        [soundvolumeview_exe, "/SetAppDefault", cable_capture_id, "all", "personaplex.exe"],
    ]
    for name in cable_capture_names:
        commands.append([soundvolumeview_exe, "/SetListenToThisDevice", name, "0"])

    for command in commands:
        try:
            subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except Exception as e:
            log.warning("SoundVolumeView failed: %s", e)

    log.info("Forced PersonaPlex capture default to CABLE Output")
