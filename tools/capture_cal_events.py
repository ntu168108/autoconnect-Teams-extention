"""
capture_cal_events.py — Lùi lịch Outlook về các tuần cũ để tìm sự kiện lớp học
thật, lấy định dạng GIỜ (phục vụ đọc lịch cho đếm ngược).

Chạy:  python3 tools/capture_cal_events.py
Kết quả: dumps/cal_events.json (+ .png)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auto_joiner as aj
import capture_calendar as cc
from selenium.webdriver.common.by import By

CAL_GUID = "ef56c0de-36fc-4ef8-b417-3d82ba9d073c"
PREV_WEEK_SEL = "[aria-label^='Đi đến tuần trước đó']"

# Mọi phần tử có aria-label chứa giờ HH:MM (lọc ra các ô sự kiện lịch).
EVENTS_JS = r"""
var out=[], seen={};
document.querySelectorAll('[aria-label]').forEach(function(e){
  var al=e.getAttribute('aria-label')||'';
  if(/\d{1,2}:\d{2}/.test(al) && al.length>12 && !seen[al]){
    seen[al]=1;
    out.push({aria: al.slice(0,220), tag: e.tagName.toLowerCase(),
              tid: e.getAttribute('data-tid')||''});
  }
});
return out.slice(0,80);
"""


def _cal_iframe(b):
    for fr in b.find_elements(By.CSS_SELECTOR, "iframe"):
        if "hwc" in (fr.get_attribute("data-tid") or "").lower():
            return fr
    return None


def main():
    os.makedirs("dumps", exist_ok=True)
    aj.load_config()
    aj.config["headless"] = False
    aj.init_browser()
    b = aj.browser
    b.get("https://teams.microsoft.com")
    print("Đăng nhập...")
    cc.try_login(b)
    aj.wait_until_found(aj.SEL_PAGE_READY, 60, print_error=False)
    time.sleep(3)

    cal = aj.wait_until_found(f"button[id='{CAL_GUID}']", 20, print_error=False)
    if cal:
        b.execute_script("arguments[0].click()", cal)
    time.sleep(2)
    deadline = time.time() + 60
    while time.time() < deadline and _cal_iframe(b) is None:
        time.sleep(2)
    time.sleep(8)  # cho Outlook render

    found, weeks_back = [], 0
    for i in range(20):
        fr = _cal_iframe(b)
        if fr is None:
            print("Không thấy iframe lịch.")
            break
        b.switch_to.frame(fr)
        try:
            evs = b.execute_script(EVENTS_JS) or []
            if evs:
                found, weeks_back = evs, i
                b.switch_to.default_content()
                break
            prev = b.find_elements(By.CSS_SELECTOR, PREV_WEEK_SEL)
            if prev:
                b.execute_script("arguments[0].click()", prev[0])
        finally:
            b.switch_to.default_content()
        print(f"  tuần -{i}: chưa thấy sự kiện, lùi tiếp...")
        time.sleep(2.5)

    json.dump({"weeks_back": weeks_back, "count": len(found), "events": found},
              open(os.path.join("dumps", "cal_events.json"), "w"),
              ensure_ascii=False, indent=2)
    try:
        b.save_screenshot(os.path.join("dumps", "cal_events.png"))
    except Exception:
        pass
    print(f"\nXONG. Lùi {weeks_back} tuần, tìm thấy {len(found)} sự kiện có giờ.")
    for e in found[:15]:
        print("   ", e["aria"][:140])
    b.quit()


if __name__ == "__main__":
    try:
        main()
    finally:
        if aj.browser:
            try:
                aj.browser.quit()
            except Exception:
                pass
