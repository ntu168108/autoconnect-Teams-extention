"""verify_peek.py — click sự kiện rồi tìm nút Tham gia ở CẢ trong iframe lẫn ngoài."""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import auto_joiner as aj
import capture_calendar as cc
CAL_GUID = "ef56c0de-36fc-4ef8-b417-3d82ba9d073c"
DUMP = r"""
var out=[];
document.querySelectorAll('button,[role="button"],a,[aria-label]').forEach(function(e){
  var t=(e.innerText||'').replace(/\s+/g,' ').trim();
  var al=e.getAttribute('aria-label')||'';
  if(/tham gia|join/i.test(t+' '+al)){
    out.push({text:t.slice(0,50), aria:al.slice(0,70), tag:e.tagName.toLowerCase(),
              tid:e.getAttribute('data-tid')||''});}
});
return out.slice(0,20);
"""
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
    fr=next((f for f in b.find_elements('css selector','iframe')
             if 'hwc' in (f.get_attribute('data-tid') or '').lower()),None)
    if not fr: print("no iframe"); b.quit(); return
    b.switch_to.frame(fr)
    labels=b.execute_script(aj._CAL_EVENTS_JS) or []
    title=None
    for al in labels:
        low=al.lower()
        if any(s in low for s in aj._CAL_SKIP): continue
        t=al.split(",")[0].strip()
        if t and not aj._CAL_TIME_RE.match(t): title=t; break
    print("click:",repr(title))
    b.execute_script(aj._JS_CLICK_EVENT,title)
    time.sleep(4)
    inside=b.execute_script(DUMP)
    b.switch_to.default_content()
    top=b.execute_script(DUMP)
    print("=== Nút 'Tham gia' TRONG iframe ==="); print(json.dumps(inside,ensure_ascii=False,indent=1))
    print("=== Nút 'Tham gia' NGOÀI iframe (top) ==="); print(json.dumps(top,ensure_ascii=False,indent=1))
    b.save_screenshot(os.path.join("dumps","peek.png")); b.quit(); print("XONG")
if __name__=="__main__":
    try: main()
    finally:
        if aj.browser:
            try: aj.browser.quit()
            except Exception: pass
