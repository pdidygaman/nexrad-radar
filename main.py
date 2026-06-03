"""
NEXRAD Radar — Desktop App launcher

Self-contained: double-click and it opens like any normal app. It starts its
own web server internally (in a background thread) on an automatically chosen
free port, shows a splash immediately, then loads the UI. Nothing to start by
hand, and it never conflicts with anything already using port 8000.

Run:  python main.py     (or just open the installed app)
"""

from __future__ import annotations
import threading
import socket
import time
import sys

import uvicorn
import webview

from app import app

HOST = '127.0.0.1'

SPLASH_HTML = """
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%;background:#070c12;color:#fff;overflow:hidden;
    font-family:'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;
    justify-content:center;flex-direction:column;gap:20px}
  .ring{width:62px;height:62px;border:4px solid rgba(0,180,255,.18);
    border-top-color:#00b4ff;border-radius:50%;animation:spin 1s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  h1{font-size:19px;font-weight:800;letter-spacing:3px;color:#00b4ff;margin:0}
  p{font-size:12px;color:rgba(255,255,255,.45);margin:0;letter-spacing:.5px}
</style></head><body>
  <div class="ring"></div>
  <h1>NEXRAD RADAR</h1>
  <p>Starting up…</p>
</body></html>
"""


def _find_free_port() -> int:
    """Pick a free TCP port. Prefer uncommon ones, then let the OS choose."""
    for candidate in (8753, 8761, 8770, 8788, 8799):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def _set_app_id():
    """
    Give the process an explicit AppUserModelID so Windows shows the app's own
    icon on the taskbar. Windows-only; no-op on macOS/Linux.
    """
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('NEXRADRadar.Viewer.1')
    except Exception:
        pass


def main():
    _set_app_id()
    port = _find_free_port()

    # Show the window with a splash IMMEDIATELY, so it feels instant.
    window = webview.create_window(
        'NEXRAD Radar',
        html=SPLASH_HTML,
        width=1500,
        height=900,
        min_size=(1100, 680),
        background_color='#070c12',
        text_select=False,
    )

    def _boot():
        # Start the embedded server in the background…
        threading.Thread(
            target=lambda: uvicorn.run(app, host=HOST, port=port, log_level='warning'),
            daemon=True,
        ).start()
        # …wait until it's ready, then swap the splash for the real UI.
        for _ in range(80):
            if _port_open(HOST, port):
                break
            time.sleep(0.25)
        try:
            window.load_url(f'http://{HOST}:{port}/')
        except Exception:
            pass

    def _on_closed():
        # Hard-exit the moment the window closes, so the server thread and the
        # WebView2 child processes die immediately (no lingering update sound).
        import os
        os._exit(0)

    window.events.closed += _on_closed

    # webview.start runs _boot once the GUI loop is up (window already visible).
    webview.start(_boot, debug=False)

    # If start() ever returns normally (all windows closed), make sure we exit.
    import os
    os._exit(0)


if __name__ == '__main__':
    main()
