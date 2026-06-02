"""verify_caljoin.py — liệt kê sự kiện đang hiển thị, click sự kiện thật đầu tiên,
rồi thử tìm nút Tham gia (kiểm chứng luồng vào lớp từ lịch)."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_joiner as aj
import capture_calendar as cc

CAL_GUID = "ef56c0de-36fc-4ef8-b417-3d82ba9d073c"

def main():
    aj.load_config(); aj.config["headless"] = False; aj.init_browser()
    b = aj.browser; b.get("https://teams.microsoft.com")
    print("Đăng nhập..."); cc.try_login(b)
    aj.wait_until_found(aj.SEL_PAGE_READY, 60, print_error=False); time.sleep(3)
    cal = aj.wait_until_found(f"button[id='{CAL_GUID}']", 20, print_error=False)
    if cal: b.execute_script("arguments[0].click()", cal)
    time.sleep(2)
    dl = time.time() + 60
    while time.time() < dl and not any('hwc' in (f.get_attribute('data-tid') or '').lower()
                                       for f in b.find_elements('css selector','iframe')):
        time.sleep(2)
    time.sleep(8)
    fr = next((f for f in b.find_elements('css selector','iframe')
               if 'hwc' in (f.get_attribute('data-tid') or '').lower()), None)
    if not fr:
        print("KHÔNG thấy iframe"); b.quit(); return
    b.switch_to.frame(fr)

    labels = b.execute_script(aj._CAL_EVENTS_JS) or []
    print("Sự kiện đang hiển thị:")
    title = None
    for al in labels:
        low = al.lower()
        if any(s in low for s in aj._CAL_SKIP): continue
        t = al.split(",")[0].strip()
        if not t or aj._CAL_TIME_RE.match(t): continue
        print("   -", al[:90])
        if title is None: title = t
    print("=> Sẽ thử click:", repr(title))

    if title:
        clicked = b.execute_script(aj._JS_CLICK_EVENT, title)
        print(f"_JS_CLICK_EVENT -> {clicked}")
        time.sleep(2.5)
        joined = b.execute_script(aj._JS_CLICK_JOIN)
        print(f"_JS_CLICK_JOIN (Tham gia) -> {joined}")
    b.switch_to.default_content()
    b.save_screenshot(os.path.join("dumps","caljoin2.png"))
    b.quit(); print("XONG -> dumps/caljoin2.png")

if __name__ == "__main__":
    try: main()
    finally:
        if aj.browser:
            try: aj.browser.quit()
            except Exception: pass
