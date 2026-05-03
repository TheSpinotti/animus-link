# Animus Link Module

Animus Link connects the Android companion app to PersonaPlex running on the Windows PC. The Android app streams microphone audio to the bridge on the Windows PC, and the bridge routes PersonaPlex audio back to the phone.

## Requirements

- Windows PC with a GPU shared by Ollama and PersonaPlex.
- Ollama running on the Windows PC for an optional local agent.
- PersonaPlex installed locally on the Windows PC.
- VB-Audio Virtual Cable for PersonaPlex input.
- Virtual Audio Driver by MTT for PersonaPlex return audio.
- Tailscale or another private route between the phone, Linux Animus host, and Windows PC.

## Ports

- `8998`: Animus Link bridge WebSocket.
- `9001`: VRAM orchestrator HTTP API.

## VRAM Orchestrator

`orchestrator.py` prevents an Ollama agent and PersonaPlex from fighting over VRAM.

States:

- `default`: Ollama agent loaded, Animus Link stopped.
- `link`: Ollama agent unloaded, Animus Link bridge running.
- `gaming`: both unloaded.

The orchestrator also exposes PersonaPlex voice control:

- `GET /voice`: returns the current voice and available built-in PersonaPlex voice IDs.
- `POST /voice`: accepts `{"voice": "NATF2", "restart_link": true}` and updates `config.toml`. When Link mode is active, the bridge restarts so PersonaPlex relaunches with the selected voice.

API:

```text
GET  /state
POST /state {"state":"default|link|gaming"}
```

The companion app enters `link` before connecting to PersonaPlex and returns to `default` when disconnecting. An Ollama runtime enters `default` before sending a chat request.

## Source Of Truth

The Linux checkout at `/home/kevin/Projects/animus-link` is the source of truth. The Windows checkout at `D:\NorthernFrostbyte\animus-link` should pull from git. Do not maintain a separate orchestrator copy in `D:\NorthernFrostbyte\animus-orchestrator` long term.

The companion app source of truth is `/home/kevin/Projects/animus-companion`.

## What Breaks Without It

Without the orchestrator, an Ollama agent and PersonaPlex can load at the same time and exhaust GPU VRAM. PersonaPlex may fail to start, the Ollama agent may unload unexpectedly, or the first request after a mode switch may stall while Ollama tears down and recreates a runner.
