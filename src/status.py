"""Thread-safe bot status + log ring buffer. Single source of truth for the
web dashboard (webui.py polls snapshot()); log() also tees to the console so
the terminal stays usable as a fallback."""

import sys
import threading
import time
from collections import deque

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


class BotStopped(Exception):
    """User pressed 'Dừng bot' on the web UI."""


_lock = threading.Lock()
stop_requested = threading.Event()

_FIELDS = {
    "state": "starting",   # starting|scanning|countdown|joining|in_meeting|idle|stopped|error
    "detail": "",          # short human text (Vietnamese)
    "title": "",           # current/next class title
    "join_at": None,       # unix ts the bot will click join (countdown target)
    "meeting_start": None, # unix ts the class starts
    "schedule": [],        # [{"title": str, "start": unix_ts}]
}
_state = dict(_FIELDS)
_logs = deque(maxlen=200)


def reset():
    """Test helper: restore pristine state."""
    global _state
    with _lock:
        _state = dict(_FIELDS)
        _logs.clear()
    stop_requested.clear()


def report(state=None, **fields):
    """Update any subset of status fields. Unknown fields are rejected."""
    with _lock:
        if state is not None:
            _state["state"] = state
        for k, v in fields.items():
            if k not in _FIELDS:
                raise KeyError(f"unknown status field: {k}")
            _state[k] = v


def log(msg):
    """Append a line to the dashboard log AND print it to the console."""
    msg = str(msg)
    with _lock:
        _logs.append({"t": time.time(), "msg": msg})
    print(msg)


def snapshot():
    with _lock:
        snap = dict(_state)
        snap["logs"] = list(_logs)
        snap["now"] = time.time()
    return snap


def check_stop():
    if stop_requested.is_set():
        raise BotStopped()


def sleep_checked(seconds):
    """time.sleep that aborts with BotStopped as soon as Stop is pressed."""
    end = time.time() + seconds
    while time.time() < end:
        check_stop()
        time.sleep(min(0.5, max(end - time.time(), 0)))
    check_stop()
