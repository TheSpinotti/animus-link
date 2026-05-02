# Animus Link

Animus Link is a small network bridge for using a local PersonaPlex voice model from another PC on the same private network.

On GPU-constrained setups, the Windows PC can also run Ollama for an optional local agent. PersonaPlex and that Ollama agent cannot both keep the GPU at the same time, so `orchestrator.py` owns the VRAM state and starts or stops the bridge as needed.

## Layout

- `src/animus_link/`: application code
- `scripts/`: Windows/Linux convenience launchers
- `docs/`: setup notes
- `orchestrator.py`: Windows VRAM orchestrator for an Ollama agent, PersonaPlex, and gaming mode
- `orchestrator_tray.py`: optional Windows tray controller for orchestrator state
- `config.example.toml`: copy to `config.toml` and edit local paths/settings

The PersonaPlex binary bundle is intentionally not stored in this repo. Point `config.toml` at the existing runtime folder.

## Quick Start

Server PC:

```powershell
cd D:\NorthernFrostbyte\animus-link
copy config.example.toml config.toml
python orchestrator.py
```

Client PC:

```bash
python -m animus_link.client 100.70.82.40
```

The companion client asks the orchestrator on port `9001` to enter `link` mode, then connects to the bridge on port `8998`.

## Source Of Truth

The Linux repo at `/home/kevin/Projects/animus-link` is the source of truth. The Windows checkout at `D:\NorthernFrostbyte\animus-link` should pull from git rather than carrying local code edits.
