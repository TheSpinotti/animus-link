"""
Animus Orchestrator Tray
Small Windows tray controller for the VRAM orchestrator.
"""

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ORCHESTRATOR_URL = "http://127.0.0.1:9001"
PYTHONW_EXE = r"C:\Users\matse\AppData\Local\Programs\Python\Python311\pythonw.exe"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

STATE_COLORS = {
    "default": (74, 200, 96),
    "link": (76, 156, 255),
    "gaming": (235, 85, 85),
    "busy": (245, 190, 70),
    "offline": (120, 120, 120),
}

STATE_LABELS = {
    "default": "Default",
    "link": "Link",
    "gaming": "Gaming",
    "busy": "Busy",
    "offline": "Offline",
}

state_lock = threading.Lock()
current_state = "offline"
is_busy = False
icon = None


def request_json(path, data=None, timeout=3):
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{ORCHESTRATOR_URL}{path}", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def make_icon(state):
    color = STATE_COLORS.get(state, STATE_COLORS["offline"])
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((6, 6, 58, 58), radius=14, fill=(24, 24, 28), outline=color, width=4)
    draw.ellipse((20, 20, 44, 44), fill=color)
    if state == "busy":
        draw.arc((16, 16, 48, 48), start=30, end=300, fill=(255, 255, 255), width=4)
    return image


def label_for(state, busy=False):
    if busy:
        return "Busy"
    return STATE_LABELS.get(state, state.title())


def refresh_icon():
    if not icon:
        return
    with state_lock:
        display_state = "busy" if is_busy else current_state
        label = label_for(current_state, is_busy)
    icon.icon = make_icon(display_state)
    icon.title = f"Animus Orchestrator: {label}"
    icon.menu = build_menu()


def poll_state():
    global current_state, is_busy
    while True:
        try:
            data = request_json("/state")
            with state_lock:
                current_state = data.get("state", "offline")
                is_busy = bool(data.get("busy"))
        except Exception:
            with state_lock:
                current_state = "offline"
                is_busy = False
        refresh_icon()
        time.sleep(2)


def set_state(state):
    global current_state, is_busy
    try:
        with state_lock:
            is_busy = True
        refresh_icon()
        request_json("/state", {"state": state})
    except Exception as exc:
        print(f"Failed to set state {state}: {exc}", flush=True)
    finally:
        time.sleep(1)
        try:
            data = request_json("/state")
            with state_lock:
                current_state = data.get("state", "offline")
                is_busy = bool(data.get("busy"))
        except Exception:
            with state_lock:
                current_state = "offline"
                is_busy = False
        refresh_icon()


def set_state_background(state):
    threading.Thread(target=set_state, args=(state,), daemon=True).start()


def restart_orchestrator(_icon=None, _item=None):
    try:
        subprocess.run(["schtasks", "/End", "/TN", "AnimusOrchestrator"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=10)
        subprocess.run(["schtasks", "/Run", "/TN", "AnimusOrchestrator"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=10)
    except Exception as exc:
        print(f"Failed to restart orchestrator: {exc}", flush=True)


def restart_tray(_icon=None, _item=None):
    subprocess.Popen(
        [sys.executable, str(Path(__file__))],
        cwd=str(Path(__file__).parent),
        creationflags=NO_WINDOW,
    )
    if icon:
        icon.stop()


def quit_tray(_icon=None, _item=None):
    if icon:
        icon.stop()


def is_checked(state):
    def checked(_item):
        with state_lock:
            return current_state == state and not is_busy
    return checked


def build_menu():
    with state_lock:
        label = label_for(current_state, is_busy)
    return pystray.Menu(
        pystray.MenuItem(f"State: {label}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Default", lambda _icon, _item: set_state_background("default"), checked=is_checked("default")),
        pystray.MenuItem("Link", lambda _icon, _item: set_state_background("link"), checked=is_checked("link")),
        pystray.MenuItem("Gaming", lambda _icon, _item: set_state_background("gaming"), checked=is_checked("gaming")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart Orchestrator", restart_orchestrator),
        pystray.MenuItem("Restart Tray App", restart_tray),
        pystray.MenuItem("Quit Tray App", quit_tray),
    )


def main():
    global icon
    icon = pystray.Icon(
        "AnimusOrchestratorTray",
        make_icon("offline"),
        "Animus Orchestrator: Offline",
        build_menu(),
    )
    threading.Thread(target=poll_state, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()
