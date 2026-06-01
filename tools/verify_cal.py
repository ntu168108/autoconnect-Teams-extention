"""verify_cal.py — kiểm chứng đọc sự kiện Lịch Outlook trên Teams thật."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_joiner as aj
import capture_calendar as cc
from datetime import datetime

def main():
    aj.load_config(); aj.config["headless"] = False; aj.init_browser()
    b = aj.browser; b.get("https://teams.microsoft.com")
    print("Đăng nhập..."); cc.try_login(b)
    aj.wait_until_found(aj.SEL_PAGE_READY, 60, print_error=False); time.sleep(3)
    evs = aj._discover_calendar_events()
    now = datetime.now()
    print(f"\n=== _discover_calendar_events: {len(evs)} sự kiện ===")
    for e in sorted(evs, key=lambda x: x["start"]):
        tag = "TƯƠNG LAI" if e["start"] > now else "đã qua/đang"
        print(f"  {e['start']:%Y-%m-%d %H:%M} [{tag}] {e['title']}")
    b.quit()

if __name__ == "__main__":
    try: main()
    finally:
        if aj.browser:
            try: aj.browser.quit()
            except Exception: pass
