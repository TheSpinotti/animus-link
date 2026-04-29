param(
  [Parameter(Mandatory = $true)]
  [string]$Server
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = "src"
python -m animus_link.client $Server --config config.toml
