@echo off
if "%~1"=="" (
  echo Usage: %~nx0 SERVER
  exit /b 2
)
cd /d "%~dp0.."
set PYTHONPATH=src
python -m animus_link.client %1 --config config.toml
