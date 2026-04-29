# Linux Client Setup

Install dependencies:

```bash
python3 -m pip install numpy sounddevice websockets
```

Run the client from the repo root:

```bash
python3 -m animus_link.client <server-tailscale-ip-or-name>
```

Example:

```bash
python3 -m animus_link.client 100.70.82.40
```
