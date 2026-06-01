"""
capture_calendar.py — Tự chụp DOM màn hình Lịch (kể cả bên trong iframe Outlook)
để tìm selector đúng cho Teams tiếng Việt.

Chạy:  python3 tools/capture_calendar.py

Script tự đăng nhập bằng email/mật khẩu trong config.json, sau đó CHỜ bạn tự bấm
vào nút "Lịch" ở thanh bên trái. Khi thấy lịch hiện ra nó tự chụp rồi thoát —
bạn không cần gõ gì trong cửa sổ Terminal.

Kết quả ghi vào: dumps/01_calendar.candidates.json  (+ .html, .png)
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auto_joiner as aj
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import inspect_teams  # cùng thư mục tools/ — dùng lại capture() đã quét được iframe


def try_login(b):
    """Đăng nhập tự động bằng config (best-effort; nếu vướng MFA thì bỏ qua,
    người dùng tự hoàn tất trong cửa sổ trình duyệt)."""
    email = aj.config.get("email", "")
    pwd = aj.config.get("password", "")
    if not (email and pwd):
        return
    try:
        e = aj.wait_until_found("input[type='email']", 30, print_error=False)
        if e:
            e.send_keys(email)
            e.send_keys(Keys.ENTER)
        p = aj.wait_until_found("input[type='password']", 15, print_error=False)
        if p:
            p.send_keys(pwd)
            p.send_keys(Keys.ENTER)
        keep = aj.wait_until_found("input[id='idBtn_Back']", 6, print_error=False)
        if keep:
            keep.click()
        use_web = aj.wait_until_found(".use-app-lnk", 5, print_error=False)
        if use_web:
            use_web.click()
    except Exception as ex:
        print("  (auto-login bỏ qua:", ex, ")")


def calendar_iframe_present(b):
    """True nếu iframe lịch (Outlook nhúng) đã xuất hiện — không phụ thuộc ngôn ngữ."""
    try:
        for fr in b.find_elements(By.CSS_SELECTOR, "iframe"):
            tid = (fr.get_attribute("data-tid") or "").lower()
            title = (fr.get_attribute("title") or "").lower()
            if "hwc" in tid or "calend" in title or "lịch" in title or "lich" in title:
                return True
    except Exception:
        pass
    return False


# GUID app Calendar trong Teams — cố định, không đổi theo ngôn ngữ
CAL_GUID = "ef56c0de-36fc-4ef8-b417-3d82ba9d073c"

# Quét RỘNG mọi aria-label trong iframe lịch (không lọc từ khóa) để thấy
# định dạng nhãn của các ô sự kiện + nút Tham gia.
BROAD_JS = r"""
var out=[];
var els=document.querySelectorAll('button,[role="button"],[role="gridcell"],a,[aria-label]');
for(var i=0;i<els.length && out.length<250;i++){
  var al=els[i].getAttribute('aria-label')||'';
  var tx=(els[i].innerText||'').trim().slice(0,60);
  if(al||tx){out.push({tag:els[i].tagName.toLowerCase(),
    tid:els[i].getAttribute('data-tid')||'', aria:al.slice(0,160), text:tx});}
}
return out;
"""


def dump_iframe_all(b, path):
    """Lưu mọi aria-label/text bên trong iframe lịch ra JSON."""
    import json
    result = []
    try:
        for fr in b.find_elements(By.CSS_SELECTOR, "iframe"):
            tid = (fr.get_attribute("data-tid") or "").lower()
            title = (fr.get_attribute("title") or "").lower()
            if not ("hwc" in tid or "calend" in title or "lịch" in title or "lich" in title):
                continue
            try:
                b.switch_to.frame(fr)
                items = b.execute_script(BROAD_JS) or []
                result.append({"data_tid": tid, "title": title, "items": items})
            finally:
                b.switch_to.default_content()
    except Exception as e:
        result.append({"error": str(e)})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    total = sum(len(r.get("items", [])) for r in result)
    print(f"  -> iframe broad dump: {total} phần tử -> {path}")


def main():
    aj.load_config()
    aj.config["headless"] = False
    aj.init_browser()
    b = aj.browser
    b.get("https://teams.microsoft.com")

    print("Đang thử đăng nhập tự động...")
    try_login(b)

    print("Chờ Teams tải xong...")
    aj.wait_until_found(aj.SEL_PAGE_READY, 60, print_error=False)
    time.sleep(3)

    # Tự bấm nút Lịch Outlook bằng GUID (không cần người dùng)
    btn = aj.wait_until_found(f"button[id='{CAL_GUID}']", 20, print_error=False)
    if btn:
        b.execute_script("arguments[0].click()", btn)
        print("Đã tự bấm 'Lịch Outlook'.")
    else:
        print("KHÔNG tìm thấy nút Lịch Outlook bằng GUID — kiểm tra lại.")

    print("Chờ iframe lịch hiện ra...")
    deadline = time.time() + 60
    while time.time() < deadline:
        if calendar_iframe_present(b):
            break
        time.sleep(2)

    # CHỜ NỘI DUNG Outlook BÊN TRONG iframe render xong (profile mới -> tải chậm).
    print("Chờ nội dung lịch Outlook render (tối đa 60s)...")
    cal_deadline = time.time() + 60
    last_n = 0
    while time.time() < cal_deadline:
        n = 0
        try:
            for fr in b.find_elements(By.CSS_SELECTOR, "iframe"):
                tid = (fr.get_attribute("data-tid") or "").lower()
                if "hwc" in tid:
                    b.switch_to.frame(fr)
                    try:
                        n = b.execute_script(
                            "return document.querySelectorAll('button,[role=\"button\"]').length;") or 0
                    finally:
                        b.switch_to.default_content()
                    break
        except Exception:
            n = 0
        print(f"  ... {n} nút trong lịch")
        if n > 30 and n == last_n:   # đã ổn định -> render xong
            break
        last_n = n
        time.sleep(3)
    time.sleep(3)

    os.makedirs("dumps", exist_ok=True)
    inspect_teams.capture(b, 2, "calendar_open")
    dump_iframe_all(b, os.path.join("dumps", "02_calendar_iframe_all.json"))
    b.quit()
    print("XONG. Xem file trong thư mục dumps/")


if __name__ == "__main__":
    try:
        main()
    finally:
        if aj.browser:
            try:
                aj.browser.quit()
            except Exception:
                pass
