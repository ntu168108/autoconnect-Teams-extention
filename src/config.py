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
    "meeting_mode": 3,          # 3 = calendar only (fastest), 2 = channels, 1 = both
    "join_before_min": 2,       # vào lớp sớm mấy phút (0 = đúng giờ)
    "headless": False,
    "mute_audio": False,
    "auto_leave_after_min": -1,
    "check_interval": 10,
    "join_message": "",
    "discord_webhook_url": "",
    # Múi giờ gửi cho API Lịch Outlook (tên theo chuẩn Windows). Chỉ dùng cho
    # đường đọc lịch nhanh; sai tên thì bot tự quay về cách đọc giao diện.
    "calendar_timezone": "SE Asia Standard Time",
    # Chờ tối đa bao lâu để bắt được token của Outlook ở lần quét đầu tiên.
    # Các lần sau không chờ lại, vì token thường đã có sẵn.
    "token_wait_seconds": 10,

    # Lớp đã bắt đầu bao lâu thì coi như đã tan, khi không biết giờ kết thúc
    # (đường đọc lịch qua API có sẵn giờ kết thúc nên không cần tới mốc này):
    "stale_after_hours": 3,

    # Rời lớp sớm khi lớp vắng dần, rồi tự chờ / vào buổi tiếp theo:
    "leave_if_last": False,          # bật kiểm tra số thành viên trong khi họp
    "min_members": 3,                # rời lớp khi số người < giá trị này (0 = tắt)
    "leave_threshold_number": -1,    # rời khi giảm >= N người so với đỉnh điểm (-1 = tắt)
    "leave_threshold_percentage": -1,  # rời khi còn < N% so với đỉnh điểm (-1 = tắt)
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


class SaveError(Exception):
    """config.json could not be written — the caller should show this
    message rather than let the raw OSError surface as a traceback."""


def save(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError as e:
        raise SaveError(
            f"Không ghi được config.json vào {get_root()}: {e.strerror or e}. "
            "Hãy chuyển thư mục bot ra khỏi nơi chỉ đọc (ví dụ ảnh đĩa .dmg "
            "chưa copy ra, hoặc thư mục không có quyền ghi) rồi thử lại."
        ) from e
