"""
capture_channel.py — Dò các kênh lớp, chụp banner "cuộc họp đã lên lịch" để biết
định dạng GIỜ thật (phục vụ tính năng đếm ngược).

Chạy:  python3 tools/capture_channel.py
Tự đăng nhập + tự dò. Kết quả: dumps/channel_meetings.json (+ ảnh).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auto_joiner as aj
import capture_calendar as cc  # try_login
from selenium.webdriver.common.by import By

TIME_NODES_JS = r"""
var b=document.querySelector(arguments[0]); if(!b) return [];
var o=[];
b.querySelectorAll('time,[datetime],[title],[aria-label]').forEach(function(e){
  o.push({tag:e.tagName.toLowerCase(), dt:e.getAttribute('datetime')||'',
          title:e.getAttribute('title')||'', aria:e.getAttribute('aria-label')||'',
          tx:(e.innerText||'').slice(0,50)});
});
return o.slice(0,40);
"""


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

    teams = aj.get_all_teams()
    print(f"Có {len(teams)} lớp. Dò từng kênh để tìm banner họp...")
    found = []
    for team in teams:
        aj.switch_to_teams_tab()
        time.sleep(1)
        card = aj.wait_until_found(
            f"[data-tid='{team.t_id}-team-card']", 5, print_error=False)
        if not card:
            continue
        b.execute_script("arguments[0].click()", card)
        time.sleep(2)
        channels = aj._get_channels_from_sidebar(team)
        for ch in channels:
            ch_btn = aj.wait_until_found(
                f"[data-tid='channel-list-item-text-{ch.c_id}']", 3, print_error=False)
            if not ch_btn:
                continue
            try:
                b.execute_script("arguments[0].click()", ch_btn)
                time.sleep(2)
            except Exception:
                continue
            banners = b.find_elements(By.CSS_SELECTOR, aj.SEL_MEETING_BANNER)
            joins = b.find_elements(By.CSS_SELECTOR, aj.SEL_CH_JOIN_BTN)
            if not (banners or joins):
                continue
            rec = {
                "team": team.name, "channel": ch.name, "join_btn": len(joins),
                "banner_aria": banners[0].get_attribute("aria-label") if banners else "",
                "banner_html": (banners[0].get_attribute("outerHTML")[:2000]
                                if banners else ""),
            }
            try:
                rec["time_nodes"] = b.execute_script(TIME_NODES_JS, aj.SEL_MEETING_BANNER)
            except Exception:
                rec["time_nodes"] = []
            found.append(rec)
            print(f"  >> {team.name} / {ch.name} | aria={rec['banner_aria'][:90]!r}")
            try:
                b.save_screenshot(os.path.join("dumps", f"channel_{len(found)}.png"))
            except Exception:
                pass
            if len(found) >= 2:
                break
        if len(found) >= 2:
            break

    json.dump(found, open(os.path.join("dumps", "channel_meetings.json"), "w"),
              ensure_ascii=False, indent=2)
    print(f"\nXONG. Tìm thấy {len(found)} banner -> dumps/channel_meetings.json")
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
