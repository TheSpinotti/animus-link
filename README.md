# Animus Link

Animus Link is a small network bridge for using a local PersonaPlex voice model from another PC on the same private network.

The server keeps a tiny launcher running. The client asks that launcher to start a one-session bridge, the bridge launches PersonaPlex, and the whole bridge session exits when the client disconnects.

## Layout

- `src/animus_link/`: application code
- `scripts/`: Windows/Linux convenience launchers
- `docs/`: setup notes
- `config.example.toml`: copy to `config.toml` and edit local paths/settings

The PersonaPlex binary bundle is intentionally not stored in this repo. Point `config.toml` at the existing runtime folder.

## Quick Start

Server PC:

```powershell
cd D:\NorthernFrostbyte\animus-link
copy config.example.toml config.toml
.\scripts\start-launcher.ps1
```

Client PC:

```bash
python -m animus_link.client 100.70.82.40
```

The client connects to the bridge if it is already running. If not, it asks the launcher on port `8997` to start it, then connects to the bridge on port `8998`.
