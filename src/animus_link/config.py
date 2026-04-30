from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class NetworkConfig:
    bridge_host: str = "0.0.0.0"
    bridge_port: int = 8998
    launcher_host: str = "0.0.0.0"
    launcher_port: int = 8997


@dataclass
class RuntimeConfig:
    personaplex_dir: str = r"C:/AI/moshi.cpp/moshi-bin-win-x64-v0.8.0-beta"
    soundvolumeview_exe: str = r"C:/AI/moshi.cpp/SoundVolumeView/SoundVolumeView.exe"


@dataclass
class PersonaPlexConfig:
    voice: str = "NATF0"
    context: int = 1000
    prompt: str = "You are a casual, low-latency local voice assistant running on Matt's Windows PC."


@dataclass
class AudioConfig:
    sample_rate: int = 24000
    frame_ms: int = 40
    loopback_frame_ms: int = 10
    input_gain: float = 4.0
    output_gain: float = 1.0
    client_mic_gain: float = 2.0
    client_play_gain: float = 2.0
    client_play_prebuffer_frames: int = 3
    client_play_max_queue_frames: int = 24

    @property
    def frame_samples(self) -> int:
        return self.sample_rate * self.frame_ms // 1000


@dataclass
class WindowsAudioConfig:
    cable_input_name: str = "CABLE Input"
    cable_output_name: str = "CABLE Output"
    cable_capture_id: str = r"VB-Audio Virtual Cable\Device\CABLE Output\Capture"
    cable_capture_aliases: list[str] = field(
        default_factory=lambda: ["CABLE Output", "VB-Audio Virtual Cable"]
    )
    personaplex_return_render_id: str = (
        r"{0.0.0.00000000}.{85D8AD2F-D7A3-4E35-9E82-61EF29C096D3}"
    )
    personaplex_return_capture_name: str = (
        "Speakers (Virtual Audio Driver by MTT) [Loopback]"
    )

    @property
    def cable_capture_names(self) -> list[str]:
        return [self.cable_capture_id, *self.cable_capture_aliases]


@dataclass
class AppConfig:
    network: NetworkConfig = field(default_factory=NetworkConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    personaplex: PersonaPlexConfig = field(default_factory=PersonaPlexConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    windows_audio: WindowsAudioConfig = field(default_factory=WindowsAudioConfig)


def _section(data: dict, key: str) -> dict:
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or "config.toml")
    data = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            data = tomllib.load(f)

    return AppConfig(
        network=NetworkConfig(**_section(data, "network")),
        runtime=RuntimeConfig(**_section(data, "runtime")),
        personaplex=PersonaPlexConfig(**_section(data, "personaplex")),
        audio=AudioConfig(**_section(data, "audio")),
        windows_audio=WindowsAudioConfig(**_section(data, "windows_audio")),
    )
