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
    personaplex_output_name: str,
) -> None:
    if not os.path.exists(soundvolumeview_exe):
        log.warning(
            "SoundVolumeView not found at %r; cannot configure CABLE device. "
            "Static may occur if 'Listen to this device' is enabled on CABLE Output.",
            soundvolumeview_exe,
        )
        return

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

    run_svv("/SetDefault", cable_capture_id, "all")
    run_svv("/SetAppDefault", cable_capture_id, "all", "personaplex.exe")
    run_svv("/SetAppDefault", personaplex_output_name, "all", "personaplex.exe")

    # If "Listen to this device" stays enabled on CABLE Output, the client's mic
    # audio loops back through the default output and the loopback captures it,
    # arriving at the client as static underneath PersonaPlex's voice.
    listen_disabled = any(
        run_svv("/SetListenToThisDevice", name, "0") for name in cable_capture_names
    )
    if not listen_disabled:
        log.warning(
            "Failed to disable 'Listen to this device' on CABLE Output — static may occur."
        )

    log.info("Forced PersonaPlex capture default to CABLE Output")
