"""Dashboard requests made while the bot is in a class: 'Rời lớp', and
'Vào ngay' on a different class (which switches to it)."""

import json
import os
import sys
import threading
import urllib.request
from datetime import datetime, timedelta
from http.server import HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import runtime as rt
import webui

_srv = None


def setup_module():
    global _srv
    _srv = HTTPServer(("127.0.0.1", 0), webui._Handler)
    threading.Thread(target=_srv.serve_forever, daemon=True).start()


def teardown_module():
    _srv.shutdown()
    _srv.server_close()


class _Meeting:
    title = "Lập trình Python"


NOW_CLASS = {"title": "Lập trình Python",
             "start": datetime.now() - timedelta(minutes=30),
             "end": datetime.now() + timedelta(minutes=60)}
NEXT_CLASS = {"title": "Cấu trúc dữ liệu",
              "start": datetime.now() + timedelta(hours=2),
              "end": datetime.now() + timedelta(hours=4)}


def setup_function():
    rt.schedule = [NOW_CLASS, NEXT_CLASS]
    rt.current_meeting = None
    rt.current_entry = None
    rt.joining = False
    rt.join_request = None
    rt.leave_request = False


def _in_class():
    rt.current_meeting = _Meeting()
    rt.current_entry = NOW_CLASS


def _post(path, payload=None):
    port = _srv.server_address[1]
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_leave_asks_the_bot_to_hang_up():
    _in_class()

    assert _post("/api/leave")["ok"] is True
    assert rt.leave_request is True


def test_leave_is_refused_when_not_in_a_class():
    res = _post("/api/leave")

    assert res["ok"] is False
    assert rt.leave_request is False


def test_join_on_another_class_is_taken_while_in_class():
    _in_class()

    assert _post("/api/join", {"idx": 1})["ok"] is True
    assert rt.join_request is NEXT_CLASS


def test_join_on_the_class_the_bot_is_in_is_refused():
    # Taking it would hang up on this very class and then drop the request as
    # a class already attended — leaving the bot out of it.
    _in_class()

    res = _post("/api/join", {"idx": 0})

    assert res["ok"] is False
    assert rt.join_request is None


def test_join_is_still_refused_while_a_join_is_in_flight():
    rt.joining = True

    assert _post("/api/join", {"idx": 1})["ok"] is False
    assert rt.join_request is None


def test_status_page_has_the_leave_button():
    port = _srv.server_address[1]
    page = urllib.request.urlopen(f"http://127.0.0.1:{port}/status").read().decode()

    assert 'id="btn-leave"' in page and "/api/leave" in page
