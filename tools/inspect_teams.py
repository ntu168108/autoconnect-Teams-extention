"""
inspect_teams.py — Diagnostic / DOM capture tool for the "new Teams" web client.

Use this when Microsoft updates Teams and the bot stops working — capture the
live DOM to find the new selectors.

Usage:
    python tools/inspect_teams.py

Then in the browser: log in -> navigate to the screen you want to inspect
(channel with meeting, calendar, pre-join screen, in-call controls)
-> switch back to terminal and press Enter to capture. Type 'q' then Enter to quit.

Checking the headcount the "leave when the class empties" rule relies on:
capture once inside a class with the People panel CLOSED, and once with it
OPEN. Each capture prints the count the bot would read, to compare with the
number Teams itself shows; the raw roster elements go into .candidates.json
under "roster".

Output goes to:  dumps/NN_<label>.html  +  .png  +  .candidates.json
"""

import json
import os
import sys

# Allow running from repo root: add src/ to path so the bot's modules import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config as config_mod
import joiner
import runtime as rt
import selectors_teams as S
from browser import init_browser
from selenium.webdriver.common.by import By

DUMP_DIR = "dumps"

CANDIDATE_JS = r"""
var KW = ['join','tham gia','meet','họp','hop','camera','micro','mic','mute',
          'audio','video','toggle','người','nguoi','people','participant',
          'roster','hang','leave','rời','roi','call','prejoin'];
function hit(s){
  s = (s || '').toLowerCase();
  for (var i = 0; i < KW.length; i++){ if (s.indexOf(KW[i]) >= 0) return true; }
  return false;
}
var els = document.querySelectorAll(
  'button,[role="button"],a,[data-tid],toggle-button,calling-join-button');
var out = [];
for (var i = 0; i < els.length; i++){
  var el = els[i];
  var al = el.getAttribute('aria-label') || '';
  var tid = el.getAttribute('data-tid') || '';
  var tx = (el.innerText || el.textContent || '').trim().slice(0, 80);
  if (hit(al) || hit(tx) || hit(tid)){
    out.push({
      tag: el.tagName.toLowerCase(),
      id: el.id || '',
      dataTid: tid,
      ariaLabel: al,
      text: tx,
      cls: el.getAttribute('class') || '',
      html: el.outerHTML.slice(0, 400)
    });
    if (out.length >= 80) break;
  }
}
return out;
"""


# The roster button, and anything in an open People panel that looks like a
# section title or a participant row — what the bot's headcount comes from.
ROSTER_JS = r"""
var out = {button: null, titles: [], rows: {}};
var btn = document.querySelector(arguments[0]);
if (btn) out.button = {
  ariaLabel: btn.getAttribute('aria-label') || '',
  title: btn.getAttribute('title') || '',
  text: (btn.innerText || '').trim(),
  html: btn.outerHTML.slice(0, 800)
};
document.querySelectorAll(
    "[class*='roster' i] [class*='title' i], [data-tid*='roster' i], [role='heading']")
  .forEach(function(el){
    if (out.titles.length >= 40) return;
    out.titles.push({
      dataTid: el.getAttribute('data-tid') || '',
      role: el.getAttribute('role') || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      text: (el.innerText || el.textContent || '').trim().slice(0, 120)
    });
  });
["[role='listitem']", "[role='treeitem']", "[data-tid^='roster-list-item']"]
  .forEach(function(sel){ out.rows[sel] = document.querySelectorAll(sel).length; });
return out;
"""


def roster_report(browser):
    """The headcount the bot would read on this screen, next to the raw
    elements it reads it from."""
    out = {}
    for name, script, args in (
            ("bot_badge_count", joiner._JS_ROSTER_BADGE_COUNT, (S.SEL_ROSTER,)),
            ("bot_panel_count", joiner._JS_ROSTER_PANEL_COUNT, ()),
            ("elements", ROSTER_JS, (S.SEL_ROSTER,))):
        try:
            out[name] = browser.execute_script(script, *args)
        except Exception as e:
            out[name] = f"<err {str(e).splitlines()[0]}>"
    return out


def capture(browser, n, label, outdir=DUMP_DIR):
    os.makedirs(outdir, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (label or "snap"))
    base = os.path.join(outdir, f"{n:02d}_{safe}")
    written = []

    try:
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(browser.page_source)
        written.append(base + ".html")
    except Exception as e:
        print(f"  ! HTML failed: {e}")

    try:
        browser.save_screenshot(base + ".png")
        written.append(base + ".png")
    except Exception as e:
        print(f"  ! screenshot failed: {e}")

    try:
        candidates = browser.execute_script(CANDIDATE_JS)
        roster = roster_report(browser)
        report = {"url": browser.current_url, "title": browser.title,
                  "candidate_count": len(candidates), "candidates": candidates,
                  "roster": roster, "iframes": []}
        elements = roster.get("elements")
        if isinstance(elements, dict) and elements.get("button"):
            print(f"  -> số người bot đọc được: từ nút = {roster['bot_badge_count']}, "
                  f"từ bảng Người = {roster['bot_panel_count']} "
                  "(so với con số Teams đang hiện)")

        # The new Teams calendar is an Outlook page embedded in an iframe, so the
        # event tiles and the Join button live INSIDE that iframe — scan each one.
        try:
            frames = browser.find_elements(By.CSS_SELECTOR, "iframe")
        except Exception:
            frames = []
        for idx, fr in enumerate(frames):
            try:
                f_tid = fr.get_attribute("data-tid") or ""
                f_title = fr.get_attribute("title") or ""
                browser.switch_to.frame(fr)
                sub = browser.execute_script(CANDIDATE_JS) or []
            except Exception as e:
                sub, f_tid, f_title = [], f"<err {e}>", ""
            finally:
                browser.switch_to.default_content()
            if sub:
                report["iframes"].append({
                    "index": idx, "data_tid": f_tid, "title": f_title,
                    "candidate_count": len(sub), "candidates": sub,
                })

        with open(base + ".candidates.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        written.append(base + ".candidates.json")
        iframe_hits = sum(fr["candidate_count"] for fr in report["iframes"])
        print(f"  -> {len(candidates)} candidates (top) + {iframe_hits} in iframes")
    except Exception as e:
        print(f"  ! candidate scan failed: {e}")

    print(f"  -> saved: {', '.join(os.path.basename(w) for w in written)}")
    return len(written)


def main():
    rt.config = config_mod.load()
    rt.config["headless"] = False
    init_browser()
    browser = rt.browser
    browser.get("https://teams.microsoft.com")

    print("\n" + "=" * 70)
    print("Log in to Teams in the Chrome window that just opened.")
    print("Navigate to the screen you want to capture, then press Enter here.")
    print("Type 'q' + Enter to quit.")
    print("=" * 70 + "\n")

    n = 0
    try:
        while True:
            label = input("Label (Enter=capture, 'q'=quit): ").strip()
            if label.lower() == "q":
                break
            n += 1
            print(f"[{n}] Capturing...")
            capture(browser, n, label)
    finally:
        browser.quit()
        print(f"\nDone. {n} captures saved to '{DUMP_DIR}/'.")


if __name__ == "__main__":
    main()
