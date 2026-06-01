"""verify_schedule.py — kiểm chứng dò lịch + parse giờ trên Teams thật."""
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
    sched = aj.discover_scheduled_meetings()
    now = datetime.now()
    print(f"\n=== Tìm thấy {len(sched)} buổi họp có giờ ===")
    for m in sorted(sched, key=lambda x: x["start"]):
        tag = "TƯƠNG LAI" if m["start"] > now else "đã qua"
        print(f"  {m['start']:%Y-%m-%d %H:%M} [{tag}] {m['title']}")
    fut = [m for m in sched if m["start"] > now]
    print(f"\n>>> Buổi TƯƠNG LAI: {len(fut)} (đây là cái bot sẽ đếm ngược)")
    b.quit()

if __name__ == "__main__":
    try: main()
    finally:
        if aj.browser:
            try: aj.browser.quit()
            except Exception: pass
