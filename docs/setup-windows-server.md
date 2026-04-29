# Windows Server Setup

1. Install Python 3.11 or newer.
2. Install dependencies:

```powershell
pip install -e .[server]
```

3. Copy `config.example.toml` to `config.toml`.
4. Confirm these paths in `config.toml`:

```toml
personaplex_dir = "C:/AI/moshi.cpp/moshi-bin-win-x64-v0.8.0-beta"
soundvolumeview_exe = "C:/AI/moshi.cpp/SoundVolumeView/SoundVolumeView.exe"
```

5. Run firewall setup from an Administrator PowerShell:

```powershell
.\scripts\install-firewall-rules.ps1
```

6. Start the launcher:

```powershell
.\scripts\start-launcher.ps1
```
