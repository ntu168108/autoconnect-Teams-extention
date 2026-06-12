"""Smoke test for webui.py: form renders, status page renders, API works,
stop endpoint sets the flag. Run directly: python tests/check_webui.py"""

import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import status
import webui

t = threading.Thread(target=webui.run_setup_gui, kwargs={"open_browser": False},
                     daemon=True)
t.start()
for _ in range(50):
    if webui._server is not None:
        break
    time.sleep(0.1)
port = webui._server.server_address[1]
base = f"http://127.0.0.1:{port}"

form = urllib.request.urlopen(base + "/").read().decode()
assert "Bắt đầu" in form, "form page broken"

stat = urllib.request.urlopen(base + "/status").read().decode()
assert "Dừng bot" in stat, "status page broken"

status.report("countdown", title="Toán", join_at=time.time() + 300)
api = json.loads(urllib.request.urlopen(base + "/api/status").read())
assert api["state"] == "countdown" and api["title"] == "Toán", "api broken"

urllib.request.urlopen(urllib.request.Request(base + "/api/stop", method="POST"))
assert status.stop_requested.is_set(), "stop flag not set"
print("webui OK")
