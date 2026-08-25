#!/usr/bin/env python3
"""Run the IPTV web player: static files + HLS proxy + availability probe.

    python3 server.py          # then open http://localhost:8777/
"""
import functools
import os
import socketserver
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from iptv_core import Handler  # noqa: E402

PORT = int(os.environ.get("IPTV_PORT", "8777"))


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    handler = functools.partial(Handler, directory=ROOT)
    with Server(("", PORT), handler) as httpd:
        print(f"IPTV player at http://localhost:{PORT}/  (serving {ROOT})")
        httpd.serve_forever()
