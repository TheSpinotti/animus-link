# Windows Server Setup

1. Install Python 3.11 or newer.
2. Install dependencies:

```powershell
pip install -e .[server]
```

3. Install the virtual audio devices:

- `VB-Audio Virtual Cable`
- `Virtual Audio Driver by MTT`

The VB-Audio cable is the PersonaPlex input bus. The MTT virtual audio driver is the PersonaPlex return bus.

4. Copy `config.example.toml` to `config.toml`.
5. Confirm these paths in `config.toml`:

```toml
personaplex_dir = "C:/AI/moshi.cpp/moshi-bin-win-x64-v0.8.0-beta"
soundvolumeview_exe = "C:/AI/moshi.cpp/SoundVolumeView/SoundVolumeView.exe"
```

6. Confirm the audio route names in `config.toml`:

```toml
cable_input_name = "CABLE Input"
cable_output_name = "CABLE Output"
cable_capture_id = "VB-Audio Virtual Cable\\Device\\CABLE Output\\Capture"
personaplex_return_render_id = "{0.0.0.00000000}.{85D8AD2F-D7A3-4E35-9E82-61EF29C096D3}"
personaplex_return_capture_name = "Speakers (Virtual Audio Driver by MTT) [Loopback]"
```

7. Run firewall setup from an Administrator PowerShell:

```powershell
.\scripts\install-firewall-rules.ps1
```

8. Start the VRAM orchestrator:

```powershell
python orchestrator.py
```

The orchestrator listens on port `9001` and owns three states:

- `default`: an Ollama agent model is loaded and the Animus Link bridge is stopped.
- `link`: an Ollama agent is unloaded and the Animus Link bridge is running for PersonaPlex.
- `gaming`: an Ollama agent and Animus Link are both unloaded.

Install it as the `AnimusOrchestrator` scheduled task on the Windows PC so it starts at login. The task should run:

```powershell
C:\Users\matse\AppData\Local\Programs\Python\Python311\python.exe orchestrator.py
```

with this start directory:

```powershell
D:\NorthernFrostbyte\animus-link
```
