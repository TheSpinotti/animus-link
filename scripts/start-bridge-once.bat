@echo off
cd /d "%~dp0.."
set PYTHONPATH=src
python -m animus_link.bridge --config config.toml
