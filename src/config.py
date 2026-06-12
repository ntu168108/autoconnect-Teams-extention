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
