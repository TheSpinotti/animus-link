"""
Animus VRAM Orchestrator
Manages GPU VRAM between Ollama (Gary) and Animus Link.

States:
  default - Ollama loaded, Animus Link stopped
  link    - Ollama unloaded, Animus Link running
  gaming  - Both unloaded

HTTP API:
  GET  /state  -> {"state": "...", "busy": bool}
  POST /state  -> body: {"state": "..."}, returns {"ok": true} immediately
"""

import json
import subprocess
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 9001
STATE_FILE = Path(__file__).parent / "state.json"
OLLAMA_URL = "http://localhost:11434"
GARY_MODEL = "qwen3.5"
GARY_NUM_CTX = 40960
GARY_THINKING = True
LINK_DIR = Path("D:/NorthernFrostbyte/animus-link")
PYTHON_EXE = r"C:\Users\matse\AppData\Local\Programs\Python\Python311\python.exe"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
LINK_CMD = [PYTHON_EXE, "-m", "animus_link.bridge", "--config", "config.toml"]

_link_proc = None
_busy = False
_lock = threading.Lock()


def get_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text()).get("state", "default")
    return "default"


def save_state(state):
    STATE_FILE.write_text(json.dumps({"state": state}))


def ollama_models():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/ps", timeout=5) as resp:
            return json.loads(resp.read()).get("models", [])
    except Exception as e:
        print(f"Ollama ps warning: {e}", flush=True)
        return []


def ollama_loaded():
    model_ref = GARY_MODEL.lower()
    model_base = model_ref.split(":", 1)[0]
    for model in ollama_models():
        names = {
            (model.get("name") or "").strip().lower(),
            (model.get("model") or "").strip().lower(),
        }
        bases = {name.split(":", 1)[0] for name in names if name}
        if model_ref in names or model_base in bases:
            loaded_ctx = model.get("context_length")
            return loaded_ctx is None or int(loaded_ctx) >= GARY_NUM_CTX
    return False


def ollama_unload():
    try:
        data = json.dumps({"model": GARY_MODEL, "keep_alive": 0}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
        print(f"Ollama: {GARY_MODEL} unloaded", flush=True)
    except Exception as e:
        print(f"Ollama unload warning: {e}", flush=True)


def ollama_load():
    if ollama_loaded():
        print(f"Ollama: {GARY_MODEL} already loaded", flush=True)
        return

    try:
        data = json.dumps({
            "model": GARY_MODEL,
            "keep_alive": -1,
            "think": GARY_THINKING,
            "options": {"num_ctx": GARY_NUM_CTX},
            "messages": [],
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=120)
        print(f"Ollama: {GARY_MODEL} loaded", flush=True)
    except Exception as e:
        print(f"Ollama load error: {e}", flush=True)


def link_running():
    return _link_proc is not None and _link_proc.poll() is None


def link_stop():
    global _link_proc
    if _link_proc:
        try:
            pid = _link_proc.pid
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=10)
            _link_proc.wait(timeout=10)
        except Exception as e:
            print(f"link_stop kill error: {e}", flush=True)
        _link_proc = None
    subprocess.run(
        [POWERSHELL, "-Command",
         "Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like '*animus_link.bridge*'} | ForEach-Object { taskkill /F /T /PID $_.ProcessId }"],
        capture_output=True, timeout=10
    )
    print("Animus Link: stopped", flush=True)


def link_start():
    global _link_proc
    if link_running():
        print(f"Animus Link: bridge already running (pid {_link_proc.pid})", flush=True)
        return

    subprocess.run(
        [POWERSHELL, "-Command",
         "Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like '*animus_link.bridge*'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True
    )
    _link_proc = subprocess.Popen(LINK_CMD, cwd=str(LINK_DIR),
                                  creationflags=subprocess.CREATE_NO_WINDOW)
    print(f"Animus Link: bridge started (pid {_link_proc.pid})", flush=True)


def transition(new_state):
    global _busy
    with _lock:
        if _busy:
            print("Already transitioning, skipping", flush=True)
            return
        _busy = True

    try:
        current = get_state()
        print(f"Transition: {current} -> {new_state}", flush=True)

        if new_state == "default":
            link_stop()
            time.sleep(1)
            ollama_load()
        elif new_state == "link":
            ollama_unload()
            time.sleep(1)
            link_start()
        elif new_state == "gaming":
            link_stop()
            if current != "gaming" or ollama_loaded():
                ollama_unload()
        else:
            raise ValueError(f"Unknown state: {new_state}")

        save_state(new_state)
        print(f"State is now: {new_state}", flush=True)
    except Exception as e:
        print(f"Transition error: {e}", flush=True)
        traceback.print_exc()
    finally:
        _busy = False


def send_json(handler, code, data):
    body = json.dumps(data).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        try:
            if self.path == "/state":
                send_json(self, 200, {"state": get_state(), "busy": _busy})
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"GET error: {e}", flush=True)

    def do_POST(self):
        try:
            if self.path == "/state":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b""
                print(f"POST /state body: {raw!r}", flush=True)
                body = json.loads(raw)
                new_state = body.get("state")
                if not new_state:
                    send_json(self, 400, {"ok": False, "error": "missing state"})
                    return
                threading.Thread(target=transition, args=(new_state,), daemon=True).start()
                send_json(self, 200, {"ok": True})
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"POST error: {e}", flush=True)
            traceback.print_exc()
            try:
                send_json(self, 500, {"ok": False, "error": str(e)})
            except Exception:
                pass


if __name__ == "__main__":
    print(f"Animus Orchestrator starting on port {PORT}", flush=True)
    print(f"Current state: {get_state()}", flush=True)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
