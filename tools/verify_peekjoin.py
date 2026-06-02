"""verify_peekjoin.py — chạy _open_calendar_meeting trên sự kiện đang hiển thị,
kiểm tra có bấm được Tham gia → hiện màn hình chờ không (KHÔNG bấm join cuối)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_joiner as aj
import capture_calendar as cc
CAL_GUID = "ef56c0de-36fc-4ef8-b417-3d82ba9d073c"

def main():
    aj.load_config(); aj.config["headless"]=False; aj.init_browser()
    b=aj.browser; b.get("https://teams.microsoft.com")
    print("login..."); cc.try_login(b)
    aj.wait_until_found(aj.SEL_PAGE_READY,60,print_error=False); time.sleep(3)
    cal=aj.wait_until_found(f"button[id='{CAL_GUID}']",20,print_error=False)
    if cal: b.execute_script("arguments[0].click()",cal)
    time.sleep(2)
    dl=time.time()+60
    while time.time()<dl and not any('hwc' in (f.get_attribute('data-tid') or '').lower()
                                     for f in b.find_elements('css selector','iframe')): time.sleep(2)
    time.sleep(8)
    # tìm tên sự kiện đang hiển thị
    fr=next((f for f in b.find_elements('css selector','iframe')
             if 'hwc' in (f.get_attribute('data-tid') or '').lower()),None)
    b.switch_to.frame(fr)
    labels=b.execute_script(aj._CAL_EVENTS_JS) or []
    title=None
    for al in labels:
        if any(s in al.lower() for s in aj._CAL_SKIP): continue
        t=al.split(",")[0].strip()
        if t and not aj._CAL_TIME_RE.match(t): title=t; break
    b.switch_to.default_content()
    print("Sự kiện đang hiển thị:", repr(title))
    if not title:
        print("Không có sự kiện hiển thị để test"); b.quit(); return
    m=aj.Meeting(m_id="test", time_started=0, title=title, calendar_meeting=True)
    ok=aj._open_calendar_meeting(m)
    print("_open_calendar_meeting (bấm được Tham gia) ->", ok)
    prejoin=aj.wait_until_found(aj.SEL_PREJOIN_SCREEN,12,print_error=False) is not None
    print("Màn hình chờ (pre-join) xuất hiện ->", prejoin)
    b.save_screenshot(os.path.join("dumps","peekjoin.png"))
    b.quit(); print("XONG (không bấm join cuối, không thực sự vào lớp)")

if __name__=="__main__":
    try: main()
    finally:
        if aj.browser:
            try: aj.browser.quit()
            except Exception: pass
