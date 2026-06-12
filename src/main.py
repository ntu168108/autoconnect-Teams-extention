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
