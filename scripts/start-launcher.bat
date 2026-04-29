@echo off
cd /d "%~dp0.."
set PYTHONPATH=src
python -m animus_link.launcher --config config.toml
