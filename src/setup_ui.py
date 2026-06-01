"""
setup_ui.py — Local web form for configuring the Teams auto-joiner.

Opens a small HTML form in a dedicated Chrome/Edge app window (served from
127.0.0.1 only), pre-filled with the current config.json values. On submit,
writes the values back to config.json and returns the merged config dict.

Minimal neutral theme with light/dark toggle and inline Lucide SVG icons.
No third-party dependencies — standard library only.
"""

import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Resolve paths relative to the repo root (one level above this file's src/ dir)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH  = os.path.join(_ROOT, "config.json")
EXAMPLE_PATH = os.path.join(_ROOT, "config.json.example")

DEFAULTS = {
    "email": "",
    "password": "",
    "meeting_mode": 3,          # 3 = calendar only (fastest)
    "headless": False,
    "mute_audio": False,
    "auto_leave_after_min": -1,
    "check_interval": 10,
    "join_message": "",
    "discord_webhook_url": "",
}

# ── Inline Lucide icons (https://lucide.dev, ISC license) ─────────────────────
ICONS = {
    "video": '<path d="m22 8-6 4 6 4V8Z"/><rect width="14" height="12" x="2" y="6" rx="2" ry="2"/>',
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "hash": '<line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/><line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "eye-off": '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/>',
    "volume-x": '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/>',
    "sliders": '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
}


def _icon(name, cls="", solid=False):
    inner = ICONS.get(name, "")
    cls_attr = f' class="{cls}"' if cls else ""
    if solid:
        return (f'<svg{cls_attr} viewBox="0 0 24 24" fill="currentColor" stroke="none" '
                f'aria-hidden="true">{inner}</svg>')
    return (f'<svg{cls_attr} viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{inner}</svg>')


STYLE = """
:root{
  --bg:#eef1f5; --card:#ffffff; --text:#1e293b; --muted:#64748b;
  --border:#e2e8f0; --field-bg:#ffffff; --field-border:#cbd5e1;
  --accent:#2563eb; --accent-weak:#eff6ff; --on-accent:#ffffff;
  --surface:#f1f5f9; --shadow:0 10px 40px rgba(15,23,42,.12);
}
[data-theme="dark"]{
  --bg:#0b1220; --card:#161e2e; --text:#e6eaf2; --muted:#93a0b5;
  --border:#2a3650; --field-bg:#0f1726; --field-border:#33415a;
  --accent:#4b82f0; --accent-weak:rgba(75,130,240,.15); --on-accent:#ffffff;
  --surface:#0f1726; --shadow:0 10px 40px rgba(0,0,0,.5);
}
*{box-sizing:border-box;}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
  padding:24px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
  background:var(--bg);color:var(--text);transition:background .2s,color .2s;}
.card{width:100%;max-width:520px;background:var(--card);border:1px solid var(--border);
  border-radius:16px;box-shadow:var(--shadow);overflow:hidden;}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:20px 24px;border-bottom:1px solid var(--border);}
.brand{display:flex;align-items:center;gap:12px;}
.brand-icon{display:flex;align-items:center;justify-content:center;width:42px;height:42px;
  border-radius:11px;background:var(--accent-weak);color:var(--accent);}
.brand-icon svg{width:22px;height:22px;}
header h1{margin:0;font-size:19px;font-weight:700;}
header p{margin:3px 0 0;font-size:13px;color:var(--muted);}
.theme-btn{display:flex;align-items:center;justify-content:center;width:38px;height:38px;
  border:1px solid var(--border);background:transparent;color:var(--text);border-radius:10px;
  cursor:pointer;transition:.15s;flex:none;}
.theme-btn:hover{background:var(--accent-weak);color:var(--accent);border-color:var(--accent);}
.theme-btn span{display:flex;}
.theme-btn svg{width:19px;height:19px;}
[data-theme="dark"] .icon-moon{display:none;}
[data-theme="light"] .icon-sun{display:none;}
form{padding:22px 24px 26px;}
label.field{display:block;margin-bottom:16px;font-size:13.5px;font-weight:600;color:var(--text);}
label.field input{width:100%;margin-top:7px;padding:11px 13px;font-size:15px;font-weight:400;
  color:var(--text);background:var(--field-bg);border:1.5px solid var(--field-border);border-radius:9px;}
label.field input::placeholder{color:var(--muted);opacity:.8;}
label.field input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-weak);}
.section-label{display:flex;align-items:center;gap:7px;font-size:13.5px;font-weight:700;
  margin:2px 0 9px;color:var(--text);}
.section-label svg{width:17px;height:17px;color:var(--muted);}
.modes{margin:0 0 16px;}
.mode{display:flex;align-items:center;gap:12px;padding:11px 13px;border:1.5px solid var(--border);
  border-radius:11px;margin-bottom:9px;cursor:pointer;transition:.15s;}
.mode:hover{border-color:var(--accent);}
.mode input{position:absolute;opacity:0;width:0;height:0;}
.mode:has(input:checked){border-color:var(--accent);background:var(--accent-weak);}
.mode-ic{display:flex;align-items:center;justify-content:center;width:36px;height:36px;flex:none;
  border-radius:9px;background:var(--surface);color:var(--muted);transition:.15s;}
.mode:has(input:checked) .mode-ic{background:var(--accent);color:var(--on-accent);}
.mode-ic svg{width:19px;height:19px;}
.mode-text{display:flex;flex-direction:column;}
.mode-title{font-weight:700;font-size:14.5px;}
.mode-sub{font-size:12.5px;color:var(--muted);margin-top:2px;}
.toggles{display:flex;flex-direction:column;gap:12px;margin:2px 0 14px;}
.switch{display:flex;align-items:center;gap:9px;font-size:14px;font-weight:600;cursor:pointer;}
.switch svg{width:17px;height:17px;color:var(--muted);}
.switch input{width:18px;height:18px;accent-color:var(--accent);margin:0;flex:none;}
details{margin:4px 0 18px;border:1px solid var(--border);border-radius:10px;padding:2px 14px;}
summary{display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:700;color:var(--muted);
  padding:10px 0;font-size:13.5px;list-style:none;}
summary::-webkit-details-marker{display:none;}
summary svg{width:16px;height:16px;}
.chev{margin-left:auto;transition:transform .2s;}
details[open] summary .chev{transform:rotate(180deg);}
details label.field{margin-top:6px;}
button.start{display:flex;align-items:center;justify-content:center;gap:9px;width:100%;padding:13px;
  font-size:15.5px;font-weight:700;color:var(--on-accent);background:var(--accent);border:none;
  border-radius:11px;cursor:pointer;transition:.15s;}
button.start:hover{filter:brightness(1.08);}
button.start svg{width:18px;height:18px;}
.done{text-align:center;padding:48px 30px;}
.done .ok{display:flex;align-items:center;justify-content:center;width:62px;height:62px;margin:0 auto 16px;
  border-radius:50%;background:var(--accent-weak);color:var(--accent);}
.done .ok svg{width:30px;height:30px;}
.done h1{margin:0 0 8px;font-size:20px;}
.done p{color:var(--muted);font-size:14px;margin:0;}
"""

THEME_HEAD = (
    "<script>(function(){try{var t=localStorage.getItem('taj-theme');"
    "if(!t)t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';"
    "document.documentElement.setAttribute('data-theme',t);}catch(e){"
    "document.documentElement.setAttribute('data-theme','light');}})();</script>"
)

TOGGLE_SCRIPT = (
    "<script>function toggleTheme(){var h=document.documentElement;"
    "var t=h.getAttribute('data-theme')==='dark'?'light':'dark';"
    "h.setAttribute('data-theme',t);try{localStorage.setItem('taj-theme',t);}catch(e){}}</script>"
)


def _doc(title, body):
    return ("<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{title}</title>" + THEME_HEAD + "<style>" + STYLE + "</style></head>"
            "<body>" + body + "</body></html>")


SUCCESS_HTML = _doc(
    "Đã lưu",
    "<div class='card'><div class='done'>"
    "<div class='ok'>" + _icon("check") + "</div>"
    "<h1>Đã lưu cấu hình</h1>"
    "<p>Bạn có thể đóng cửa sổ này và quay lại terminal —<br>bot đang khởi động.</p>"
    "</div></div>"
    "<script>setTimeout(function(){try{window.close();}catch(e){}},1500);</script>"
)


def _load_config():
    for path in (CONFIG_PATH, EXAMPLE_PATH):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _render_form(cfg):
    email = _esc(cfg.get("email", ""))
    password = _esc(cfg.get("password", ""))
    try:
        mode = int(cfg.get("meeting_mode", 3) or 3)
    except (ValueError, TypeError):
        mode = 3

    def ck(v):
        return "checked" if mode == v else ""

    ckhl = "checked" if cfg.get("headless") else ""
    ckma = "checked" if cfg.get("mute_audio") else ""
    auto_leave = _esc(cfg.get("auto_leave_after_min", -1))
    interval = _esc(cfg.get("check_interval", 10))
    join_msg = _esc(cfg.get("join_message", ""))
    discord = _esc(cfg.get("discord_webhook_url", ""))

    body = f"""
<div class="card">
  <header>
    <div class="brand">
      <span class="brand-icon">{_icon("video")}</span>
      <div>
        <h1>Teams Auto-Joiner</h1>
        <p>Điền thông tin rồi bấm Bắt đầu</p>
      </div>
    </div>
    <button type="button" class="theme-btn" onclick="toggleTheme()" title="Đổi giao diện sáng / tối" aria-label="Đổi giao diện sáng tối">
      <span class="icon-moon">{_icon("moon")}</span><span class="icon-sun">{_icon("sun")}</span>
    </button>
  </header>
  <form method="post" action="/" autocomplete="off">
    <label class="field">Email
      <input type="email" name="email" value="{email}" placeholder="ban@truong.edu.vn" autofocus>
    </label>
    <label class="field">Mật khẩu
      <input type="password" name="password" value="{password}" placeholder="••••••••">
    </label>

    <div class="section-label">{_icon("search")} Nguồn tìm cuộc họp</div>
    <div class="modes">
      <label class="mode">
        <input type="radio" name="meeting_mode" value="3" {ck(3)}>
        <span class="mode-ic">{_icon("calendar")}</span>
        <span class="mode-text">
          <span class="mode-title">Chỉ Lịch</span>
          <span class="mode-sub">Nhanh nhất — thấy nút Join ngay trên lịch</span>
        </span>
      </label>
      <label class="mode">
        <input type="radio" name="meeting_mode" value="2" {ck(2)}>
        <span class="mode-ic">{_icon("hash")}</span>
        <span class="mode-text">
          <span class="mode-title">Chỉ Kênh</span>
          <span class="mode-sub">Quét từng kênh của từng team — chậm hơn</span>
        </span>
      </label>
      <label class="mode">
        <input type="radio" name="meeting_mode" value="1" {ck(1)}>
        <span class="mode-ic">{_icon("layers")}</span>
        <span class="mode-text">
          <span class="mode-title">Cả hai</span>
          <span class="mode-sub">Lịch + Kênh</span>
        </span>
      </label>
    </div>

    <div class="toggles">
      <label class="switch"><input type="checkbox" name="headless" {ckhl}>{_icon("eye-off")} Chạy ẩn (headless)</label>
      <label class="switch"><input type="checkbox" name="mute_audio" {ckma}>{_icon("volume-x")} Tắt loa trình duyệt</label>
    </div>

    <details>
      <summary>{_icon("sliders")} Nâng cao {_icon("chevron", cls="chev")}</summary>
      <label class="field">Tự rời họp sau (phút, -1 = không tự rời)
        <input type="number" name="auto_leave_after_min" value="{auto_leave}">
      </label>
      <label class="field">Khoảng quét lại (giây)
        <input type="number" name="check_interval" value="{interval}" min="2">
      </label>
      <label class="field">Lời nhắn khi vào họp (để trống = không gửi)
        <input type="text" name="join_message" value="{join_msg}">
      </label>
      <label class="field">Discord webhook URL (tùy chọn)
        <input type="text" name="discord_webhook_url" value="{discord}">
      </label>
    </details>

    <button type="submit" class="start">{_icon("play", solid=True)} Bắt đầu</button>
  </form>
</div>
{TOGGLE_SCRIPT}
"""
    return _doc("Teams Auto-Joiner — Cấu hình", body)


class _Handler(BaseHTTPRequestHandler):
    config = {}
    submitted = None
    result = {}

    def log_message(self, *args):
        pass  # silence default request logging

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            self._send_html(_render_form(_Handler.config))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
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
        cfg["meeting_mode"] = as_int("meeting_mode", 3)
        cfg["headless"] = "headless" in form
        cfg["mute_audio"] = "mute_audio" in form
        cfg["auto_leave_after_min"] = as_int("auto_leave_after_min", -1)
        cfg["check_interval"] = as_int("check_interval", 10)
        cfg["join_message"] = g("join_message")
        cfg["discord_webhook_url"] = g("discord_webhook_url")

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        _Handler.result = cfg
        self._send_html(SUCCESS_HTML)
        if _Handler.submitted is not None:
            _Handler.submitted.set()


def _browser_path():
    """Locate a Chromium-based browser (Chrome or Edge) for app-window mode."""
    try:
        import winreg
        reg_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        ]
        for hive, key in reg_keys:
            try:
                with winreg.OpenKey(hive, key) as k:
                    val, _ = winreg.QueryValueEx(k, None)
                    if val and os.path.exists(val):
                        return val
            except OSError:
                continue
    except Exception:
        pass

    for c in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(c):
            return c
    return None


def _open_app_window(url):
    """Open the form in a dedicated Chrome/Edge app window (no tabs/address bar)."""
    exe = _browser_path()
    if not exe:
        return False
    import subprocess
    import tempfile
    profile = os.path.join(tempfile.gettempdir(), "taj_setup_profile")
    try:
        subprocess.Popen([
            exe,
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=640,960",
        ])
        return True
    except Exception:
        return False


def run_setup_gui(open_browser=True):
    """Show the config form, block until submitted, return the merged config."""
    cfg = {**DEFAULTS, **_load_config()}
    _Handler.config = cfg
    _Handler.submitted = threading.Event()
    _Handler.result = cfg

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("\n" + "=" * 62)
    print("  Đang mở form cấu hình trong cửa sổ riêng...")
    print(f"  Nếu không tự mở, hãy mở link này: {url}")
    print("=" * 62 + "\n")

    if open_browser:
        # Prefer a dedicated Chrome/Edge app window (separate from the user's
        # normal browsing tabs); fall back to the default browser if not found.
        if not _open_app_window(url):
            try:
                webbrowser.open(url)
            except Exception:
                pass

    try:
        _Handler.submitted.wait()
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(0.4)  # let the success response flush to the browser
        server.shutdown()

    return _Handler.result


if __name__ == "__main__":
    print(json.dumps(run_setup_gui(), ensure_ascii=False, indent=2))
