from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from animus_link.config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("animus_link.launcher")

_lock = threading.Lock()
_bridge: subprocess.Popen | None = None
_config_path = "config.toml"
_repo_root = Path(__file__).resolve().parents[2]


def bridge_running() -> bool:
    return _bridge is not None and _bridge.poll() is None


def start_bridge() -> tuple[int, str]:
    global _bridge
    with _lock:
        if bridge_running():
            return 200, "bridge already running\n"
        command = [
            sys.executable,
            "-m",
            "animus_link.bridge",
            "--config",
            _config_path,
        ]
        log.info("Starting bridge: %s", " ".join(command))
        env = os.environ.copy()
        src_path = str(_repo_root / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        _bridge = subprocess.Popen(
            command,
            cwd=str(_repo_root),
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        return 200, f"started bridge pid={_bridge.pid}\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
        elif self.path == "/start":
            status, text = start_bridge()
            body = text.encode("utf-8")
            self.send_response(status)
        else:
            body = b"not found\n"
            self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animus Link remote launcher")
    parser.add_argument("--config", default="config.toml", help="Path to config TOML")
    return parser.parse_args()


def main():
    global _config_path, _repo_root
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    _config_path = str(config_path)
    _repo_root = config_path.parent
    config = load_config(config_path)
    host = config.network.launcher_host
    port = config.network.launcher_port
    log.info("Listening on http://%s:%s", host, port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
