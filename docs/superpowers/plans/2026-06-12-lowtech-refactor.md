# Lowtech Refactor + 1-Click Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `src/auto_joiner.py` (1127 lines) into focused modules, turn the one-shot setup form into a persistent web dashboard (countdown / schedule / log / Stop button), and ship 1-click binaries for Windows + macOS via GitHub Actions.

**Architecture:** Shared mutable state lives in `runtime.py`; a thread-safe `status.py` feeds a stdlib HTTP server (`webui.py`) that serves the config form, then a live status page polling `/api/status`. Selenium logic is MOVED verbatim (verified against live Teams — do not rewrite behavior), with two mechanical transforms: module-globals become `rt.<name>` and user-facing `print(...)` becomes `status.log(...)`.

**Tech Stack:** Python 3.8+ stdlib + `selenium` + `requests` (drop `discord.py`), `pytest` for new pure-python modules, PyInstaller onefile, GitHub Actions (`windows-latest`, `macos-latest`).

**Repo root:** `C:\Users\tupc\Downloads\autoconnect-Teams-extention`. All line numbers below refer to `src/auto_joiner.py` and `src/setup_ui.py` at commit `0f0b803`.

---

## Mechanical transform rules (used by every "move" task)

When moving code out of `auto_joiner.py`:

1. **Globals → runtime.** Add `import runtime as rt` and rewrite references:
   `browser` → `rt.browser`, `config` → `rt.config`, `meetings` → `rt.meetings`,
   `current_meeting` → `rt.current_meeting`, `already_joined_ids` → `rt.already_joined_ids`,
   `_handled` → `rt.handled`, `hangup_thread` → `rt.hangup_thread`, `mode` → `rt.mode`,
   `channel_to_team` → `rt.channel_to_team`, `total_members` → `rt.total_members`.
   Delete all `global X` statements (attribute assignment on `rt` needs no global).
2. **print → status.log.** Every user-facing `print(...)` in moved bot code becomes
   `status.log(...)` (add `import status`). EXCEPTIONS that stay as raw
   `sys.stdout.write`/`print`: the live one-line countdown writes inside
   `_countdown_until` (lines 1030–1053) — those repaint a single line and must not
   land in the log buffer.
3. **Selectors/JS** come from `import selectors_teams as S` → `S.SEL_...`, `S._JS_...`
   (module is named `selectors_teams.py` because stdlib already owns `selectors`).
4. Keep every sleep, timeout, selector string, regex, and JS snippet byte-identical.

---

### Task 1: `runtime.py` + `status.py` (with tests)

**Files:**
- Create: `src/runtime.py`
- Create: `src/status.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_status.py
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import status


def setup_function(_):
    status.reset()


def test_report_and_snapshot():
    status.report("countdown", title="Toán", join_at=123.0, detail="Còn 5 phút")
    snap = status.snapshot()
    assert snap["state"] == "countdown"
    assert snap["title"] == "Toán"
    assert snap["join_at"] == 123.0
    assert snap["detail"] == "Còn 5 phút"


def test_partial_report_keeps_other_fields():
    status.report("countdown", title="Toán", join_at=123.0)
    status.report(detail="chỉ đổi detail")
    snap = status.snapshot()
    assert snap["state"] == "countdown"
    assert snap["title"] == "Toán"
    assert snap["detail"] == "chỉ đổi detail"


def test_log_appends_and_caps(capsys):
    for i in range(250):
        status.log(f"msg {i}")
    snap = status.snapshot()
    assert len(snap["logs"]) == 200
    assert snap["logs"][-1]["msg"] == "msg 249"
    assert "msg 249" in capsys.readouterr().out


def test_check_stop_raises():
    status.stop_requested.set()
    try:
        status.check_stop()
        assert False, "should have raised"
    except status.BotStopped:
        pass


def test_sleep_checked_aborts_quickly():
    status.stop_requested.set()
    try:
        status.sleep_checked(30)
        assert False, "should have raised"
    except status.BotStopped:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_status.py -v` (install first: `python -m pip install pytest`)
Expected: FAIL with `ModuleNotFoundError: No module named 'status'`

- [ ] **Step 3: Write the implementation**

```python
# src/runtime.py
"""Shared mutable bot state. Other modules do `import runtime as rt`."""

browser = None            # selenium webdriver, set by browser.init_browser()
config = {}               # merged config dict, set by main
meetings = []
current_meeting = None
already_joined_ids = []
handled = set()           # class sessions already joined/attempted this run
channel_to_team = {}      # {channel_thread_id: team_thread_id}
hangup_thread = None      # threading.Timer for auto-leave
mode = 3
total_members = None
```

```python
# src/status.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_status.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime.py src/status.py tests/test_status.py
git commit -m "feat: shared runtime state + thread-safe status/log module"
```

---

### Task 2: `config.py` (frozen-aware paths) + `notify.py` (drop discord.py)

**Files:**
- Create: `src/config.py`
- Create: `src/notify.py`
- Create: `tests/test_config.py`
- Create: `tests/test_notify.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config as config_mod


def test_root_is_repo_root_when_not_frozen():
    root = config_mod.get_root()
    assert os.path.isfile(os.path.join(root, "requirements.txt"))


def test_root_is_exe_dir_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\apps\bot\TeamsAutoJoiner.exe")
    assert config_mod.get_root() == os.path.abspath(r"C:\apps\bot")


def test_load_merges_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"email": "a@b.c", "blacklist": [{"team_name": "X"}]}),
        encoding="utf-8")
    cfg = config_mod.load()
    assert cfg["email"] == "a@b.c"
    assert cfg["meeting_mode"] == 1          # default filled in
    assert cfg["blacklist"] == [{"team_name": "X"}]  # untouched keys preserved


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "get_root", lambda: str(tmp_path))
    config_mod.save({"email": "x@y.z", "password": "s3cret"})
    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["email"] == "x@y.z"
```

```python
# tests/test_notify.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import notify
import runtime as rt


def test_no_url_no_post(monkeypatch):
    rt.config = {}
    called = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: called.append(a))
    notify.discord_notification("t", "d")
    assert called == []


def test_posts_embed(monkeypatch):
    rt.config = {"discord_webhook_url": "https://discord.test/hook", "email": "a@b.c"}
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        class R:
            status_code = 204
        return R()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.discord_notification("Joined meeting", "Toán")
    assert captured["url"] == "https://discord.test/hook"
    embed = captured["json"]["embeds"][0]
    assert embed["title"] == "Joined meeting"
    assert embed["description"] == "Toán"
    assert "a@b.c" in embed["footer"]["text"]


def test_post_errors_swallowed(monkeypatch):
    rt.config = {"discord_webhook_url": "https://discord.test/hook"}

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify.requests, "post", boom)
    notify.discord_notification("t", "d")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'config'` (then `notify`)

- [ ] **Step 3: Write the implementations**

```python
# src/config.py
"""Config load/save with frozen-aware paths.

When packaged by PyInstaller (onefile), __file__ points into a temp _MEIPASS
dir that is DELETED on exit — config.json must live next to the executable
instead so settings survive between runs."""

import json
import os
import sys

DEFAULTS = {
    "email": "",
    "password": "",
    "meeting_mode": 1,          # 1 = both (channels + calendar)
    "join_before_min": 2,       # vào lớp sớm mấy phút (0 = đúng giờ)
    "headless": False,
    "mute_audio": False,
    "auto_leave_after_min": -1,
    "check_interval": 10,
    "join_message": "",
    "discord_webhook_url": "",
}


def get_root():
    if getattr(sys, "frozen", False):                 # PyInstaller bundle
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path():
    return os.path.join(get_root(), "config.json")


def example_path():
    return os.path.join(get_root(), "config.json.example")


def load():
    """Return DEFAULTS overlaid with config.json (or config.json.example)."""
    cfg = dict(DEFAULTS)
    for path in (config_path(), example_path()):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    cfg.update(json.load(f))
                break
            except Exception:
                continue
    return cfg


def save(cfg):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
```

```python
# src/notify.py
"""Discord webhook notifications via a plain HTTP POST.

Replaces the discord.py dependency: a webhook message is just JSON POSTed to
the webhook URL, and dropping discord.py removes aiohttp & friends from the
PyInstaller bundle (~30 MB smaller, fewer install failures)."""

from datetime import datetime

import requests

import runtime as rt


def discord_notification(title, description):
    url = rt.config.get("discord_webhook_url", "")
    if not url:
        return
    payload = {
        "embeds": [{
            "title": str(title),
            "description": str(description),
            "color": 0x0011FF,
            "author": {"name": "Ms-Teams-Auto-Joiner-Bot"},
            "footer": {"text": (f"\nTime: [{datetime.now():%Y:%m:%d-%H:%M:%S}]"
                                f"\nlogin-id: {rt.config.get('email', '')}")},
        }]
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        print("Failed to send discord notification")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all tests pass (status + config + notify)

- [ ] **Step 5: Commit**

```bash
git add src/config.py src/notify.py tests/test_config.py tests/test_notify.py
git commit -m "feat: frozen-aware config module + requests-based discord notify"
```

---

### Task 3: `selectors_teams.py` + `models.py` (pure moves)

**Files:**
- Create: `src/selectors_teams.py`
- Create: `src/models.py`

- [ ] **Step 1: Create `src/selectors_teams.py`**

Copy from `src/auto_joiner.py`, byte-identical:
- Lines 44 (`uuid_regex`) and 46–68 (all `SEL_*` constants)
- Lines 70–115 (`_JS_CAL_EVENTS`, `_JS_CLICK_EVENT`, `_JS_CLICK_JOIN` with their comments)
- Lines 922–933 (`_CAL_EVENTS_JS`, `_CAL_SKIP`)

Add this module docstring at the top:

```python
"""Every CSS selector and JS snippet used against new Teams / Outlook.

This is THE file to edit when Microsoft changes the Teams UI. Selectors were
derived from live DOM dumps (2026-05/06) and verified on a real account —
change them only against a fresh dump (see tools/inspect_teams.py)."""
```

- [ ] **Step 2: Create `src/models.py`**

Copy from `src/auto_joiner.py`, lines 118–176 (`Channel`, `Team`, `Meeting` classes),
with one transform: both classes read the global `config` — apply rule 1
(`config` → `rt.config`, add `import re` and `import runtime as rt` at top).
The header is:

```python
"""Data classes shared by scanner / joiner / schedule."""

import re

import runtime as rt
```

(Inside `Team.check_blacklist`: `blacklist = rt.config.get('blacklist', [])`;
inside `Meeting._check_blacklist_calendar`: `rt.config.get('blacklist_meeting_re')`
and `rt.config['blacklist_meeting_re']`.)

- [ ] **Step 3: Verify imports**

Run: `python -c "import sys; sys.path.insert(0,'src'); import selectors_teams, models; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/selectors_teams.py src/models.py
git commit -m "refactor: extract selectors and data classes into modules"
```

---

### Task 4: `browser.py` (move)

**Files:**
- Create: `src/browser.py`

- [ ] **Step 1: Create `src/browser.py`**

Header:

```python
"""Chrome/Edge lifecycle, login, and wait helpers."""

import time

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import runtime as rt
import selectors_teams as S
import status
from notify import discord_notification
```

Move these functions from `auto_joiner.py`, applying transform rules 1–3:
- `init_browser` (lines 187–230)
- `wait_until_found` (250–259), `wait_present` (262–271)
- `switch_to_teams_tab` (276–281), `switch_to_calendar_tab` (283–287)
- `change_organisation` (292–318)
- `_browser_dead` (1186–1198) — rename to `browser_dead` (it's used by `main.py`)
- `open_and_login` (1201–1247)

Concrete transform examples (the executor applies the same pattern throughout):
- `browser = webdriver.Edge(...)` → `rt.browser = webdriver.Edge(...)`, drop `global browser`
- `SEL_PAGE_READY` → `S.SEL_PAGE_READY`
- `print("Enabled headless mode")` → `status.log("Enabled headless mode")`
- In `open_and_login`, the two-part progress print
  (`print("Waiting for Teams to load…", end='')` … `print("\rTeams loaded. …")`)
  becomes two plain `status.log(...)` calls:
  `status.log("Đang chờ Teams tải xong…")` and
  `status.log("Teams đã tải xong. Đừng bấm gì vào cửa sổ Chrome.")`
- At the very top of `open_and_login`, add `status.report("starting", detail="Đang mở Chrome và đăng nhập…")`.

- [ ] **Step 2: Verify import**

Run: `python -c "import sys; sys.path.insert(0,'src'); import browser; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/browser.py
git commit -m "refactor: extract browser lifecycle/login into browser.py"
```

---

### Task 5: `scanner.py` (move)

**Files:**
- Create: `src/scanner.py`

- [ ] **Step 1: Create `src/scanner.py`**

Header:

```python
"""Discover classes: channel meeting banners + Outlook calendar events."""

import re
import time
from datetime import datetime

from selenium.common import exceptions
from selenium.webdriver.common.by import By

import runtime as rt
import selectors_teams as S
import status
from browser import (switch_to_calendar_tab, switch_to_teams_tab,
                     wait_until_found)
from models import Channel, Meeting, Team
```

Move from `auto_joiner.py`, applying transform rules:
- `get_all_teams` (323–344)
- `_get_channels_from_sidebar` (347–368)
- `get_meetings` (371–439)
- `get_calendar_meetings` (442–492)
- `_BANNER_DT_RE` + `_parse_banner_time` (834–846)
- `discover_scheduled_meetings` (860–911)
- `_CAL_TIME_RE`, `_CAL_DATE_RE` (918–919) and `_parse_calendar_time` (936–951)
- `_discover_calendar_events` (954–995)

Notes:
- `_JS_CAL_EVENTS` → `S._JS_CAL_EVENTS`; `_CAL_EVENTS_JS` → `S._CAL_EVENTS_JS`; `_CAL_SKIP` → `S._CAL_SKIP`.
- `meetings.append(...)` → `rt.meetings.append(...)`; `already_joined_ids` → `rt.already_joined_ids`; `channel_to_team[c_id] = team.t_id` → `rt.channel_to_team[c_id] = team.t_id`; drop `global` lines.

- [ ] **Step 2: Verify import**

Run: `python -c "import sys; sys.path.insert(0,'src'); import scanner; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/scanner.py
git commit -m "refactor: extract schedule/calendar discovery into scanner.py"
```

---

### Task 6: `joiner.py` (move)

**Files:**
- Create: `src/joiner.py`

- [ ] **Step 1: Create `src/joiner.py`**

Header:

```python
"""Join a class: open it (channel or calendar), pre-join (cam/mic off),
send the optional join message, leave, and count participants."""

import random
import time
from threading import Timer

from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import runtime as rt
import selectors_teams as S
import status
from browser import (switch_to_calendar_tab, switch_to_teams_tab,
                     wait_present, wait_until_found)
from notify import discord_notification
```

Move from `auto_joiner.py`, applying transform rules:
- `decide_meeting` (497–515)
- `_prejoin_turn_off_camera` (520–534), `_prejoin_mute_mic` (537–552)
- `_open_calendar_meeting` (557–588)
- `_open_meeting_chat` (591–615)
- `join_meeting` (618–720)
- `get_meeting_members` (725–778)
- `hangup` (781–796)
- `handle_leave_threshold` (799–824)

Notes:
- In `join_meeting`: `hangup_thread = Timer(...)` → `rt.hangup_thread = Timer(...)`;
  `current_meeting = meeting` → `rt.current_meeting = meeting`;
  `already_joined_ids.append(...)` → `rt.already_joined_ids.append(...)`.
- After the join click succeeds (right before `print(f"Joined meeting: ...")`,
  which becomes `status.log(...)`), add:
  `status.report("in_meeting", title=meeting.title, detail="Đang trong lớp")`.
- In `hangup`, after `rt.current_meeting = None`, add:
  `status.report("idle", detail="Đã rời lớp")`.

- [ ] **Step 2: Verify import**

Run: `python -c "import sys; sys.path.insert(0,'src'); import joiner; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/joiner.py
git commit -m "refactor: extract meeting join/leave logic into joiner.py"
```

---

### Task 7: `schedule.py` (move + status hooks + stop checks)

**Files:**
- Create: `src/schedule.py`

- [ ] **Step 1: Create `src/schedule.py`**

Header:

```python
"""Main loop: discover → countdown → join early → stay → repeat."""

import sys
import time
from datetime import datetime, timedelta

import runtime as rt
import selectors_teams as S
import status
from browser import switch_to_teams_tab, wait_until_found
from joiner import (decide_meeting, get_meeting_members,
                    handle_leave_threshold, hangup, join_meeting)
from models import Meeting
from notify import discord_notification
from scanner import (_discover_calendar_events, discover_scheduled_meetings,
                     get_all_teams, get_meetings)
```

Move from `auto_joiner.py`, applying transform rules:
- `_fmt_td` (849–857)
- `_join_live_channel_meeting` (998–1009) — `meetings = []` becomes `rt.meetings = []`
- `_countdown_until` (1012–1054)
- `_stay_until_meeting_ends` (1057–1079)
- `run_schedule_loop` (1082–1181)

Then add status/stop integration (exact edits):

1. `_countdown_until` — at the top of the function body add:
```python
    status.report("countdown",
                  title=meeting.get("title") or "Buổi học",
                  join_at=join_at.timestamp(),
                  meeting_start=meeting["start"].timestamp(),
                  detail=f"Tự vào lúc {join_at:%H:%M}")
```
   and as the FIRST line inside its `while time.time() < end:` loop add
   `status.check_stop()`.

2. `_stay_until_meeting_ends` — first line inside `while rt.current_meeting is not None:`
   add `status.check_stop()`; replace the final `time.sleep(interval)` with
   `status.sleep_checked(interval)`.

3. `run_schedule_loop` — exact insertions:
   - First line inside `while True:` add `status.check_stop()` and replace
     `print("\nĐang dò lịch học… chờ chút")` with
     `status.report("scanning", detail="Đang dò lịch học…")` +
     `status.log("Đang dò lịch học… chờ chút")`.
   - After `schedule = list(by_start.values())` add:
```python
        status.report(schedule=[
            {"title": m["title"], "start": m["start"].timestamp()}
            for m in sorted(schedule, key=lambda m: m["start"])])
```
   - In the `if not upcoming:` branch, before the sleep add
     `status.report("idle", detail=f"Chưa thấy buổi học sắp tới — quét lại sau {mins} phút")`
     and replace `time.sleep(rescan_seconds)` with `status.sleep_checked(rescan_seconds)`.
   - At "Tới giờ vào lớp" add `status.report("joining", title=nxt["title"], detail="Đang vào lớp…")`.
   - Replace `time.sleep(20)` in the retry loop with `status.sleep_checked(20)`.

- [ ] **Step 2: Verify import**

Run: `python -c "import sys; sys.path.insert(0,'src'); import schedule; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/schedule.py
git commit -m "refactor: extract main loop into schedule.py with status + stop hooks"
```

---

### Task 8: `webui.py` (form + status dashboard + API)

**Files:**
- Create: `src/webui.py`

- [ ] **Step 1: Create `src/webui.py` — carried-over parts**

Copy UNCHANGED from `src/setup_ui.py`:
- `ICONS` dict + `_icon()` (lines 46–71) — ADD two icons to the dict:
```python
    "square": '<rect width="14" height="14" x="5" y="5" rx="2"/>',
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
```
- `STYLE` (74–154), `THEME_HEAD` (156–161), `TOGGLE_SCRIPT` (163–167), `_doc()` (170–174)
- `_load_config` is REPLACED by `config.load` (import `config as config_mod`)
- `_esc` (199–201), `_render_form` (204–303) — unchanged except the form's submit
  button row gains nothing; keep as is
- `_find_browser` (364–420), `_open_app_window` (423–448), `_SETUP_PROFILE_MARKER` (453)
- DROP `_close_app_window` and `SUCCESS_HTML` entirely (window now stays open
  showing the dashboard).

Module header:

```python
"""Local web UI: config form (/) → live status dashboard (/status).

Stdlib-only HTTP server bound to 127.0.0.1. The server stays alive for the
whole bot run; the dashboard polls /api/status every 2 s and the countdown
ticks client-side."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import config as config_mod
import status
```

- [ ] **Step 2: Add the status page + new handler**

Append this CSS to the end of `STYLE`:

```css
.status-wrap{max-width:560px;}
.big-state{display:flex;align-items:center;gap:12px;padding:20px 24px;}
.big-state .dot{width:12px;height:12px;border-radius:50%;background:var(--accent);flex:none;
  animation:pulse 1.6s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.big-state h2{margin:0;font-size:18px;}
.big-state p{margin:2px 0 0;font-size:13px;color:var(--muted);}
.countdown{font-variant-numeric:tabular-nums;font-size:44px;font-weight:800;
  text-align:center;padding:6px 0 14px;letter-spacing:1px;}
.sched{padding:0 24px 8px;}
.sched h3{font-size:13px;color:var(--muted);margin:8px 0 6px;text-transform:uppercase;letter-spacing:.4px;}
.sched ul{list-style:none;margin:0;padding:0;}
.sched li{display:flex;justify-content:space-between;gap:10px;padding:7px 10px;border:1px solid var(--border);
  border-radius:9px;margin-bottom:6px;font-size:13.5px;}
.sched li .when{color:var(--muted);flex:none;}
.logbox{margin:10px 24px 16px;background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:10px 12px;height:180px;overflow-y:auto;font-size:12.5px;line-height:1.55;
  font-family:Consolas,Menlo,monospace;white-space:pre-wrap;}
.btn-stop{display:flex;align-items:center;justify-content:center;gap:9px;margin:0 24px 22px;padding:12px;
  font-size:15px;font-weight:700;color:#fff;background:#dc2626;border:none;border-radius:11px;
  cursor:pointer;width:calc(100% - 48px);}
.btn-stop:hover{filter:brightness(1.1);}
.btn-stop:disabled{opacity:.5;cursor:default;}
```

Add the status page builder:

```python
def _render_status_page():
    body = f"""
<div class="card status-wrap">
  <header>
    <div class="brand">
      <span class="brand-icon">{_icon("activity")}</span>
      <div>
        <h1>Teams Auto-Joiner</h1>
        <p>Bảng theo dõi — để cửa sổ này mở</p>
      </div>
    </div>
    <button type="button" class="theme-btn" onclick="toggleTheme()" title="Đổi giao diện sáng / tối">
      <span class="icon-moon">{_icon("moon")}</span><span class="icon-sun">{_icon("sun")}</span>
    </button>
  </header>
  <div class="big-state"><span class="dot" id="dot"></span>
    <div><h2 id="state-line">Đang khởi động…</h2><p id="detail-line"></p></div>
  </div>
  <div class="countdown" id="countdown" hidden>--:--:--</div>
  <div class="sched"><h3>Lịch đã dò được</h3><ul id="sched-list"><li>Chưa có dữ liệu</li></ul></div>
  <div class="sched"><h3>Nhật ký hoạt động</h3></div>
  <div class="logbox" id="logbox"></div>
  <button class="btn-stop" id="btn-stop">{_icon("square")} Dừng bot</button>
</div>
{TOGGLE_SCRIPT}
<script>
var STATE_VI = {{
  starting:   "Đang khởi động…",
  scanning:   "Đang dò lịch học…",
  countdown:  "Đếm ngược tới buổi học",
  joining:    "Đang vào lớp…",
  in_meeting: "Đang trong lớp",
  idle:       "Đang chờ",
  stopped:    "Bot đã dừng",
  error:      "Có lỗi xảy ra"
}};
var joinAt = null, clockOff = 0, stopped = false;

function fmt(t) {{
  t = Math.max(0, Math.round(t));
  var h = Math.floor(t/3600), m = Math.floor(t%3600/60), s = t%60;
  function p(n) {{ return (n<10?"0":"")+n; }}
  return (h? h+":" : "") + p(m) + ":" + p(s);
}}

function tick() {{
  var el = document.getElementById("countdown");
  if (joinAt && !stopped) {{
    el.hidden = false;
    el.textContent = fmt(joinAt - (Date.now()/1000 - clockOff));
  }} else {{ el.hidden = true; }}
}}
setInterval(tick, 500);

function render(s) {{
  clockOff = Date.now()/1000 - s.now;
  joinAt = (s.state === "countdown") ? s.join_at : null;
  var line = STATE_VI[s.state] || s.state;
  if (s.title && (s.state === "countdown" || s.state === "in_meeting" || s.state === "joining"))
    line += " — " + s.title;
  document.getElementById("state-line").textContent = line;
  document.getElementById("detail-line").textContent = s.detail || "";
  var ul = document.getElementById("sched-list");
  if (s.schedule && s.schedule.length) {{
    ul.innerHTML = "";
    s.schedule.forEach(function(m) {{
      var d = new Date(m.start*1000);
      var li = document.createElement("li");
      var name = document.createElement("span"); name.textContent = m.title;
      var when = document.createElement("span"); when.className = "when";
      when.textContent = d.toLocaleString("vi-VN", {{hour:"2-digit",minute:"2-digit",day:"2-digit",month:"2-digit"}});
      li.appendChild(name); li.appendChild(when); ul.appendChild(li);
    }});
  }}
  var box = document.getElementById("logbox");
  var atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
  box.textContent = (s.logs || []).map(function(l) {{
    var d = new Date(l.t*1000);
    function p(n) {{ return (n<10?"0":"")+n; }}
    return "[" + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds()) + "] " + l.msg;
  }}).join("\\n");
  if (atBottom) box.scrollTop = box.scrollHeight;
  if (s.state === "stopped") {{
    stopped = true;
    document.getElementById("dot").style.animation = "none";
    document.getElementById("btn-stop").disabled = true;
    document.getElementById("btn-stop").textContent = "Bot đã dừng — có thể đóng cửa sổ này";
  }}
}}

function poll() {{
  fetch("/api/status").then(function(r) {{ return r.json(); }}).then(render)
    .catch(function() {{
      if (!stopped) {{
        document.getElementById("state-line").textContent = "Bot đã thoát";
        document.getElementById("detail-line").textContent = "Có thể đóng cửa sổ này.";
      }}
    }});
}}
setInterval(poll, 2000); poll();

document.getElementById("btn-stop").onclick = function() {{
  if (!confirm("Dừng bot? Bot sẽ rời lớp (nếu đang trong lớp) và đóng Chrome.")) return;
  fetch("/api/stop", {{method: "POST"}});
  this.disabled = true; this.textContent = "Đang dừng…";
}};
</script>
"""
    return _doc("Teams Auto-Joiner — Theo dõi", body)
```

Replace the old `_Handler` with:

```python
class _Handler(BaseHTTPRequestHandler):
    config = {}
    submitted = None
    result = {}

    def log_message(self, *args):
        pass

    def _send_html(self, html, code=200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send_html(_render_form(_Handler.config))
        elif path == "/status":
            self._send_html(_render_status_page())
        elif path == "/api/status":
            self._send_json(status.snapshot())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/stop":
            status.stop_requested.set()
            status.log("Đã nhận yêu cầu dừng từ trang theo dõi.")
            self._send_json({"ok": True})
            return

        # POST / — save config, then show the dashboard in the same window
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw, keep_blank_values=True)

        def g(key, default=""):
            return form.get(key, [default])[0]

        def as_int(key, default):
            try:
                return int(g(key, str(default)) or default)
            except ValueError:
                return default

        cfg = dict(_Handler.config)  # preserve untouched keys (blacklist, etc.)
        cfg["email"] = g("email")
        cfg["password"] = g("password")
        cfg["meeting_mode"] = as_int("meeting_mode", 1)
        cfg["join_before_min"] = as_int("join_before_min", 2)
        cfg["headless"] = "headless" in form
        cfg["mute_audio"] = "mute_audio" in form
        cfg["auto_leave_after_min"] = as_int("auto_leave_after_min", -1)
        cfg["check_interval"] = as_int("check_interval", 10)
        cfg["join_message"] = g("join_message")
        cfg["discord_webhook_url"] = g("discord_webhook_url")

        config_mod.save(cfg)
        _Handler.result = cfg

        self.send_response(303)          # See Other → GET /status
        self.send_header("Location", "/status")
        self.end_headers()
        if _Handler.submitted is not None:
            _Handler.submitted.set()
```

And replace `run_setup_gui` with:

```python
_server = None


def run_setup_gui(open_browser=True):
    """Serve the form, block until submitted, return the merged config.
    The server KEEPS RUNNING afterwards to power /status."""
    global _server
    cfg = config_mod.load()
    _Handler.config = cfg
    _Handler.submitted = threading.Event()
    _Handler.result = cfg

    _server = HTTPServer(("127.0.0.1", 0), _Handler)
    url = f"http://127.0.0.1:{_server.server_address[1]}/"

    threading.Thread(target=_server.serve_forever, daemon=True).start()

    print("\n" + "=" * 62)
    print("  Đang mở form cấu hình trong cửa sổ riêng...")
    print(f"  Nếu không tự mở, hãy mở link này: {url}")
    print("=" * 62 + "\n")

    if open_browser:
        if not _open_app_window(url):
            try:
                webbrowser.open(url)
            except Exception:
                pass

    try:
        _Handler.submitted.wait()
    except KeyboardInterrupt:
        pass
    return _Handler.result


def start_headless_server():
    """--no-gui runs still get the dashboard: start the server without
    opening a window and log the URL."""
    global _server
    _Handler.config = config_mod.load()
    _server = HTTPServer(("127.0.0.1", 0), _Handler)
    url = f"http://127.0.0.1:{_server.server_address[1]}/status"
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    status.log(f"Bảng theo dõi: {url}")
```

- [ ] **Step 3: Automated check**

```bash
python - <<'EOF'
import sys, threading, time, urllib.request, json
sys.path.insert(0, "src")
import webui, status

t = threading.Thread(target=webui.run_setup_gui, kwargs={"open_browser": False}, daemon=True)
t.start()
time.sleep(1)
port = webui._server.server_address[1]
base = f"http://127.0.0.1:{port}"

form = urllib.request.urlopen(base + "/").read().decode()
assert "Bắt đầu" in form, "form page broken"

stat = urllib.request.urlopen(base + "/status").read().decode()
assert "Dừng bot" in stat, "status page broken"

status.report("countdown", title="Toán", join_at=time.time()+300)
api = json.loads(urllib.request.urlopen(base + "/api/status").read())
assert api["state"] == "countdown" and api["title"] == "Toán"

urllib.request.urlopen(urllib.request.Request(base + "/api/stop", method="POST"))
assert status.stop_requested.is_set(), "stop flag not set"
print("webui OK")
EOF
```

Expected: `webui OK`
(On Windows run it as a temp file: save to `tests\check_webui.py` without the heredoc and `python tests\check_webui.py`. Keep the file as `tests/check_webui.py` — it's the webui smoke test.)

- [ ] **Step 4: Commit**

```bash
git add src/webui.py tests/check_webui.py
git commit -m "feat: web UI status dashboard with countdown, schedule, log, stop button"
```

---

### Task 9: `main.py`, delete old files, update launchers + requirements

**Files:**
- Create: `src/main.py`
- Delete: `src/auto_joiner.py`, `src/setup_ui.py`
- Modify: `run.bat`, `run.command`, `requirements.txt`

- [ ] **Step 1: Create `src/main.py`**

```python
"""Entry point: config (GUI or --no-gui) → login → schedule loop.

All failure modes end with a short Vietnamese message, never a traceback."""

import sys
import time
from datetime import datetime
from getpass import getpass

import config as config_mod
import runtime as rt
import status
import webui
from browser import browser_dead, open_and_login
from notify import discord_notification
from schedule import run_schedule_loop

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    rt.mode = rt.config.get("meeting_mode", 1)
    if not (0 < rt.mode < 4):
        rt.mode = 1

    email = rt.config.get("email", "")
    password = rt.config.get("password", "")
    if not email:
        email = input("Email: ")
    if not password:
        password = getpass("Password: ")

    open_and_login(email, password)
    run_schedule_loop()


if __name__ == "__main__":
    use_gui = "--no-gui" not in sys.argv

    if use_gui:
        rt.config = webui.run_setup_gui()
    else:
        rt.config = config_mod.load()
        webui.start_headless_server()

    if rt.config.get("run_at_time"):
        now = datetime.now()
        run_at = datetime.strptime(rt.config["run_at_time"], "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        if run_at.time() < now.time():
            run_at = run_at.replace(day=now.day + 1)
        delay = (run_at - now).total_seconds()
        status.log(f"Chờ đến {run_at} ({int(delay)} giây)")
        time.sleep(delay)

    exit_msg = ""
    try:
        main()
    except KeyboardInterrupt:
        exit_msg = "Đã dừng bot. Tạm biệt!"
    except status.BotStopped:
        exit_msg = "Bot đã dừng theo yêu cầu từ trang theo dõi."
    except Exception as e:
        if browser_dead(e):
            exit_msg = "Chrome đã đóng nên bot dừng lại. Mở lại bot để chạy tiếp."
        else:
            status.report("error", detail=str(e)[:200])
            status.log(f"Lỗi không mong muốn: {e}")
            raise
    finally:
        try:
            if rt.browser:
                rt.browser.quit()
        except Exception:
            pass
        if rt.hangup_thread:
            try:
                rt.hangup_thread.cancel()
            except Exception:
                pass
        if exit_msg:
            status.log(exit_msg)
        status.report("stopped", detail=exit_msg or "Bot đã dừng.")
        try:
            discord_notification("Browser closed", "Thank you!")
        except Exception:
            pass
        time.sleep(3)   # let the dashboard pick up the 'stopped' state
```

- [ ] **Step 2: Delete the old monolith and update launchers**

```bash
git rm src/auto_joiner.py src/setup_ui.py
```

In `run.bat` line 24 change `%PY% -c "import selenium, discord, requests" >nul 2>nul`
to `%PY% -c "import selenium, requests" >nul 2>nul`, and line 31
`%PY% src/auto_joiner.py %*` to `%PY% src/main.py %*`.

In `run.command` lines 33 and 38 change
`"$PY" -c "import selenium, requests; from discord import SyncWebhook" 2>/dev/null`
to `"$PY" -c "import selenium, requests" 2>/dev/null`, and line 83
`"$PY" src/auto_joiner.py "$@"` to `"$PY" src/main.py "$@"`.

Overwrite `requirements.txt` with:

```
selenium>=4.6
requests
```

- [ ] **Step 3: Full smoke test**

```bash
python -m pytest tests/ -v
python tests/check_webui.py
python -c "import sys; sys.path.insert(0,'src'); import main" 
```

Expected: all tests pass, `webui OK`, the `import main` exits silently
(the `__main__` guard prevents the bot from starting).

- [ ] **Step 4: Live smoke (manual, with real config.json present)**

Run `run.bat`. Verify: form opens → Bắt đầu → window switches to the dashboard
→ Chrome opens and logs in → dashboard shows "Đang dò lịch học…" then a countdown
→ press "Dừng bot" → Chrome closes, dashboard shows "Bot đã dừng", console exits
cleanly.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: new main.py entry point, drop monolith + discord.py dep"
```

---

### Task 10: Local build scripts + Windows build verify

**Files:**
- Create: `build_local.bat`
- Create: `build_local.command`

- [ ] **Step 1: Create `build_local.bat`**

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Build Teams Auto-Joiner (Windows) ===
python -m pip install --upgrade pyinstaller selenium requests || goto :err
python -m PyInstaller --onefile --console --name TeamsAutoJoiner --distpath dist --workpath build --specpath build src/main.py || goto :err
copy /y config.json.example dist\ >nul
echo.
echo Xong! File: dist\TeamsAutoJoiner.exe
pause
exit /b 0
:err
echo BUILD LOI — xem thong bao phia tren.
pause
exit /b 1
```

- [ ] **Step 2: Create `build_local.command`**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=== Build Teams Auto-Joiner (macOS) ==="
python3 -m pip install --upgrade pyinstaller selenium requests
python3 -m PyInstaller --onefile --console --name TeamsAutoJoiner \
  --distpath dist --workpath build --specpath build src/main.py
cp config.json.example dist/
cat > "dist/Chạy bot.command" <<'EOF'
#!/bin/bash
cd "$(dirname "$0")"
./TeamsAutoJoiner
echo ""
echo "=== Bot đã dừng. Nhấn phím bất kỳ để đóng. ==="
read -n 1 -s -r
EOF
chmod +x "dist/Chạy bot.command" dist/TeamsAutoJoiner
echo "Xong! Thư mục: dist/"
```

(`git update-index --chmod=+x build_local.command` after adding, so it stays executable.)

- [ ] **Step 3: Build and verify on this Windows machine**

```bash
./build_local.bat   # or run it by double-click
dist/TeamsAutoJoiner.exe
```

Expected: exe starts, console shows the config-form banner, browser app window
opens the form. Submit with empty email/password is NOT needed — close the
console after the form appears (this verifies frozen paths + bundled imports).
Also verify `config.json` would land next to the exe:
`python -c "import sys; sys.path.insert(0,'src'); import config; print(config.config_path())"`
prints the repo path when unfrozen (frozen behavior is covered by tests/test_config.py).

- [ ] **Step 4: Add `dist/` and `build/` to `.gitignore`, commit**

Append to `.gitignore`:

```
dist/
build/
```

```bash
git add build_local.bat build_local.command .gitignore
git update-index --chmod=+x build_local.command
git commit -m "build: local PyInstaller build scripts for Windows and macOS"
```

---

### Task 11: GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `packaging/HUONG-DAN.txt`

- [ ] **Step 1: Create `packaging/HUONG-DAN.txt`**

```
TEAMS AUTO-JOINER — HƯỚNG DẪN NHANH

WINDOWS:
 1. Double-click TeamsAutoJoiner.exe
 2. Nếu Windows hiện cảnh báo xanh "Windows protected your PC":
    bấm "More info" → "Run anyway" (app chưa mua chữ ký số, không phải virus).
 3. Form cấu hình hiện ra → điền Email/Mật khẩu → bấm Bắt đầu.

MACOS:
 1. Double-click "Chạy bot.command"
 2. Lần đầu nếu bị chặn: chuột phải vào file → Open → Open.
    (Hoặc System Settings → Privacy & Security → Open Anyway)
 3. Form cấu hình hiện ra → điền Email/Mật khẩu → bấm Bắt đầu.

LƯU Ý:
 - Cần có Google Chrome hoặc Microsoft Edge trên máy.
 - Đừng bấm gì vào cửa sổ Chrome mà bot mở.
 - Theo dõi bot ở trang "Bảng theo dõi" (tự mở trong trình duyệt).
 - Muốn dừng: bấm nút "Dừng bot" trên trang theo dõi.
 - File config.json (cạnh file chạy) chứa mật khẩu của bạn — KHÔNG gửi cho ai.
```

- [ ] **Step 2: Create `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: windows-latest
            zip: TeamsAutoJoiner-Windows.zip
          - os: macos-latest
            zip: TeamsAutoJoiner-macOS.zip
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install deps
        run: python -m pip install -r requirements.txt pyinstaller

      - name: Build binary
        run: >
          python -m PyInstaller --onefile --console --name TeamsAutoJoiner
          --distpath dist --workpath build --specpath build src/main.py

      - name: Package (Windows)
        if: runner.os == 'Windows'
        shell: pwsh
        run: |
          Copy-Item config.json.example dist/
          Copy-Item packaging/HUONG-DAN.txt dist/
          Compress-Archive -Path dist/* -DestinationPath ${{ matrix.zip }}

      - name: Package (macOS)
        if: runner.os == 'macOS'
        run: |
          cp config.json.example packaging/HUONG-DAN.txt dist/
          cat > "dist/Chạy bot.command" <<'EOF'
          #!/bin/bash
          cd "$(dirname "$0")"
          ./TeamsAutoJoiner
          echo ""
          echo "=== Bot đã dừng. Nhấn phím bất kỳ để đóng. ==="
          read -n 1 -s -r
          EOF
          chmod +x "dist/Chạy bot.command" dist/TeamsAutoJoiner
          cd dist && zip -r "../${{ matrix.zip }}" .

      - name: Upload to release
        uses: softprops/action-gh-release@v2
        with:
          files: ${{ matrix.zip }}
          generate_release_notes: true
```

- [ ] **Step 3: Validate YAML locally**

Run: `python -c "import yaml,io; yaml.safe_load(io.open('.github/workflows/release.yml',encoding='utf-8')); print('yaml ok')"`
(if PyYAML missing: `python -m pip install pyyaml`)
Expected: `yaml ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml packaging/HUONG-DAN.txt
git commit -m "ci: build Windows/macOS one-click zips on tag push"
```

---

### Task 12: README rewrite for download-first flow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite the install section**

Replace the entire "Cài đặt & chạy" section (README.md lines 59–93) with:

```markdown
## Cài đặt & chạy

### Cách 1 — Tải bản dựng sẵn (KHUYÊN DÙNG, không cần cài gì)

1. Vào trang **[Releases](https://github.com/ntu168108/autoconnect-Teams-extention/releases)** → tải file cho máy bạn:
   - Windows: `TeamsAutoJoiner-Windows.zip`
   - macOS: `TeamsAutoJoiner-macOS.zip`
2. **Giải nén** ra một thư mục bất kỳ.
3. Double-click:
   - Windows: `TeamsAutoJoiner.exe` — nếu hiện cảnh báo xanh, bấm **More info → Run anyway**.
   - macOS: `Chạy bot.command` — lần đầu bị chặn thì **chuột phải → Open → Open**.
4. Form cấu hình hiện ra → điền **Email / Mật khẩu** → bấm **▶ Bắt đầu**.
5. Trang chuyển thành **Bảng theo dõi**: đếm ngược, lịch học, nhật ký, nút **Dừng bot**. Để cửa sổ này mở.

> Máy cần có **Google Chrome** hoặc **Microsoft Edge** (hầu hết máy có sẵn).

### Cách 2 — Chạy từ mã nguồn (cần Python 3.8+)

```bash
pip install -r requirements.txt
```

Rồi double-click `run.bat` (Windows) hoặc `run.command` (macOS).
```

Also update the developer file table (lines 190–198): `auto_joiner.py` →
the new module list (`main.py`, `schedule.py`, `scanner.py`, `joiner.py`,
`browser.py`, `selectors_teams.py`, `webui.py`, `config.py`, `status.py`,
`notify.py`, `models.py`, `runtime.py`), and note that selectors live in
`src/selectors_teams.py`. Update the inspect command to `python tools/inspect_teams.py`.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: download-first install guide for prebuilt releases"
```

---

### Task 13: Final verification + release

- [ ] **Step 1: Full test suite + smoke**

```bash
python -m pytest tests/ -v
python tests/check_webui.py
```

Expected: all pass.

- [ ] **Step 2: Real run-through (manual)**

`run.bat` end-to-end once more with the real account: form → dashboard →
login → countdown appears → Stop button works.

- [ ] **Step 3: Push + tag**

The user pushes from their own terminal (GitHub auth is not available in this
sandbox — see memory note from 2026-06-01):

```bash
git push origin main
git tag v1.0.0
git push origin v1.0.0
```

Then check the Actions tab: both jobs green, Release page has both zips.
Download `TeamsAutoJoiner-Windows.zip` on this machine and verify it runs;
the user verifies the macOS zip on their Mac.
