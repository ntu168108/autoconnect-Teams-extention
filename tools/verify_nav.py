"""verify_nav.py — kiểm chứng selector mới: mở được Nhóm/Teams + Lịch không."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auto_joiner as aj
import capture_calendar as cc  # dùng lại try_login


def main():
    aj.load_config()
    aj.config["headless"] = False
    aj.init_browser()
    b = aj.browser
    b.get("https://teams.microsoft.com")

    print("Đăng nhập...")
    cc.try_login(b)
    aj.wait_until_found(aj.SEL_PAGE_READY, 60, print_error=False)
    time.sleep(3)

    # 1) Nav Nhóm/Teams (cần cho chế độ Kênh)
    aj.switch_to_teams_tab()
    time.sleep(2)
    grid = aj.wait_until_found(aj.SEL_TEAMS_GRID, 10, print_error=False)
    teams = aj.get_all_teams()
    print(f"\n>>> NHÓM/TEAMS: grid={'OK' if grid else 'FAIL'} | so_team_tim_thay={len(teams)}")
    for t in teams[:6]:
        print("      -", t.name)

    # 2) Nav Lịch/Calendar (cần cho chế độ Lịch)
    aj.switch_to_calendar_tab()
    time.sleep(3)
    iframe = aj.wait_until_found(aj.SEL_CAL_IFRAME, 15, print_error=False)
    print(f">>> LỊCH/CALENDAR: iframe={'OK' if iframe else 'FAIL'}")

    print("\nKET QUA:",
          "CA HAI NAV OK" if (teams and iframe) else "CON LOI - xem tren")
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
