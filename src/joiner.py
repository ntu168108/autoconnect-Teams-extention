"""Join a class: open it (channel or calendar), pre-join (cam/mic off),
send the optional join message, leave, and count participants."""

import random
import time
from threading import Timer
from urllib.parse import quote

from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import runtime as rt
import selectors_teams as S
import status
from browser import (browser_dead, switch_to_calendar_tab, switch_to_teams_tab,
                     wait_present, wait_until_found)
from notify import discord_notification


def _prejoin_turn_off_camera():
    """
    Camera toggle is a Fluent UI Switch <input> (visually hidden -> use presence).
    Camera is ON when aria-checked == "true", or the title offers to turn it OFF.
    """
    inp = wait_present(S.SEL_TOGGLE_VIDEO, 6)
    if inp is None:
        return
    title = (inp.get_attribute("title") or "").lower()
    checked = (inp.get_attribute("aria-checked") or "").lower()
    camera_on = (checked == "true"
                 or "turn camera off" in title or "tắt camera" in title)
    if camera_on:
        rt.browser.execute_script("arguments[0].click()", inp)
        status.log("Camera turned off")


def _prejoin_mute_mic():
    """
    Mic toggle is a Fluent UI Switch <input> (visually hidden -> use presence).
    Mic is ON (unmuted) when aria-checked == "true", or the title offers to MUTE.
    """
    inp = wait_present(S.SEL_TOGGLE_MUTE, 6)
    if inp is None:
        return
    title = (inp.get_attribute("title") or "").lower()
    checked = (inp.get_attribute("aria-checked") or "").lower()
    offers_mute = "mute mic" in title or "tắt micrô" in title or "tắt tiếng" in title
    offers_unmute = "unmute" in title or "bật micrô" in title or "bật tiếng" in title
    mic_on = (checked == "true" or offers_mute) and not offers_unmute
    if mic_on:
        rt.browser.execute_script("arguments[0].click()", inp)
        status.log("Microphone muted")


def _open_meeting_by_link(meeting):
    """Open the class through its own Teams join link and stop at the pre-join
    screen. Returns False if we do not have the ids, or the screen never came.

    Preferred over hunting for the event in the rendered calendar: the calendar
    only shows the week on screen and has to be matched by title text, whereas
    the ids come straight from the calendar API and address the meeting
    exactly. It costs a page load, so the caller keeps the calendar route as
    the fallback."""
    thread_id = getattr(meeting, "thread_id", None)
    if not thread_id:
        return False

    reply_id = getattr(meeting, "reply_id", None) or 0
    # The "_#" segment loads the web client straight away. The plain
    # /l/meetup-join/ form instead serves Teams' launcher page, which embeds an
    # <iframe src="msteams:..."> to hand off to the desktop app — and that
    # makes Chrome raise a native "Open Microsoft Teams?" dialog that sits over
    # the window and cannot be dismissed from selenium.
    url = (f"https://teams.microsoft.com/_#/l/meetup-join/"
           f"{quote(thread_id, safe='')}/{reply_id}")
    status.log("Đang mở lớp bằng link trực tiếp…")
    try:
        rt.browser.get(url)
    except Exception as e:
        if browser_dead(e):
            raise
        status.log(f"Không mở được link lớp: {str(e).splitlines()[0]}")
        _return_to_teams()
        return False

    # A meetup-join link can land in several different places, so work out
    # which one we got and react, rather than assuming it opened the class:
    #   * the pre-join screen            → done
    #   * Teams' launcher page           → press "continue in this browser"
    #   * the Teams app on some other    → the deep link did not carry through;
    #     view (home, teams grid, …)       hand over to the calendar route, and
    #                                      crucially do NOT reload, because the
    #                                      app we need is already loaded
    #   * anything else / nothing        → reload Teams so the fallback has an
    #                                      app to work with
    clicked_web = False
    app_ready_since = None
    deadline = time.time() + 60
    while time.time() < deadline:
        if wait_until_found(S.SEL_PREJOIN_SCREEN, 3, print_error=False) is not None:
            return True

        if not clicked_web:
            btn = wait_until_found(S.SEL_LAUNCHER_JOIN_WEB, 2, print_error=False)
            if btn is not None:
                status.log("Bỏ qua trang trung gian — tiếp tục trên trình duyệt này.")
                rt.browser.execute_script("arguments[0].click()", btn)
                clicked_web = True
                continue

        if wait_until_found(S.SEL_PAGE_READY, 2, print_error=False) is not None:
            # Teams is up. Give the class a grace period to open on its own
            # before deciding the deep link simply did not take.
            if app_ready_since is None:
                app_ready_since = time.time()
            elif time.time() - app_ready_since > 20:
                status.log("Link chỉ mở được Teams chứ không vào thẳng lớp — "
                           "chuyển qua Lịch (không phải tải lại).")
                return False

    status.log("Link trực tiếp không mở được màn hình vào lớp — thử qua Lịch.")
    _return_to_teams()
    return False


def _return_to_teams():
    """Go back to the Teams app after a failed link attempt.

    The link navigates the whole window away, so the calendar fallback would
    otherwise run against the launcher page and fail with 'Calendar iframe not
    found' — the fallback needs the app back before it can do anything."""
    try:
        rt.browser.get("https://teams.microsoft.com")
    except Exception as e:
        if browser_dead(e):
            raise
        return
    if wait_until_found(S.SEL_PAGE_READY, 60, print_error=False) is None:
        status.log("Teams tải lại chậm sau khi thử link — sẽ thử lại ở vòng sau.")


def _open_calendar_meeting(meeting):
    """Open the event peek in the calendar iframe and click its Join button.

    Returns True if Join was clicked (the Teams pre-join screen should then
    appear in the main app). Always returns with the driver on default content.
    """
    switch_to_calendar_tab()
    time.sleep(3)

    iframe = wait_until_found(S.SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        status.log("Calendar iframe not found")
        return False

    rt.browser.switch_to.frame(iframe)
    try:
        time.sleep(1)
        label = getattr(meeting, "cal_label", "") or meeting.title
        if not rt.browser.execute_script(S._JS_CLICK_EVENT, label):
            status.log(f"Could not open calendar event: {meeting.title}")
            return False
        # The peek/callout renders asynchronously — poll up to ~14s for its
        # "Tham gia cuộc họp Teams" button instead of a single fixed wait.
        time.sleep(2)
        for _ in range(6):
            if rt.browser.execute_script(S._JS_CLICK_JOIN):
                return True
            time.sleep(2)
        status.log("Could not find the Join button in the calendar peek")
        return False
    finally:
        rt.browser.switch_to.default_content()


def _open_meeting_chat():
    """Open the IN-MEETING chat panel (the side panel, NOT the app-bar Chat tab).

    The only safe way to open meeting chat is via the toolbar inside the meeting
    (data-tid='ubar-horizontal-middle-end'). We wait up to 15 s for that toolbar
    to appear, then find the Chat button within it. We never fall back to a bare
    'button[aria-label="Chat"]' search because that catches the left app-bar button
    which minimises the meeting window and opens personal chat.
    """
    # Wait for the in-meeting toolbar to be present first
    toolbar = wait_present("[data-tid='ubar-horizontal-middle-end']", 15)
    if toolbar is None:
        status.log("In-meeting toolbar not found — cannot open meeting chat")
        return False

    # Find the Chat button *inside* the toolbar only
    try:
        btn = toolbar.find_element(By.CSS_SELECTOR, "button[aria-label^='Chat']")
    except exceptions.NoSuchElementException:
        status.log("Chat button not found inside meeting toolbar")
        return False

    rt.browser.execute_script("arguments[0].click()", btn)
    time.sleep(2)
    return True


def _cancel_auto_leave():
    """Kill any pending auto-leave timer.

    A class that ends on its own never goes through hangup(), so its timer
    outlives it. Left armed, it fires mid-way through a LATER class and hangs
    that one up early — so clear it before arming a new one."""
    if rt.hangup_thread is not None:
        rt.hangup_thread.cancel()
        rt.hangup_thread = None


def join_meeting(meeting):
    hangup()
    _cancel_auto_leave()

    # ── Reach the pre-join screen ──────────────────────────────────────────
    if meeting.calendar_meeting:
        # Its own join link first — exact, and not limited to the calendar week
        # currently on screen. Falls back to clicking the event in the calendar.
        if not (_open_meeting_by_link(meeting) or _open_calendar_meeting(meeting)):
            return
        # Either route leaves us on (or heading to) the pre-join screen.
    else:
        # Navigate to the right team then the right channel
        switch_to_teams_tab()
        time.sleep(1)

        team_id = meeting.team_id or rt.channel_to_team.get(meeting.channel_id)
        if team_id:
            card = wait_until_found(
                f"[data-tid='{team_id}-team-card']", 5, print_error=False)
            if card:
                rt.browser.execute_script("arguments[0].click()", card)
                time.sleep(2)

        ch_btn = wait_until_found(
            f"[data-tid='channel-list-item-text-{meeting.channel_id}']",
            5, print_error=False)
        if ch_btn:
            rt.browser.execute_script("arguments[0].click()", ch_btn)
            time.sleep(2)

        join_btn = wait_until_found(S.SEL_CH_JOIN_BTN, 10)
        if join_btn is None:
            status.log(f"Could not find join button for: {meeting.title}")
            return
        rt.browser.execute_script("arguments[0].click()", join_btn)

    # ── Pre-join screen ────────────────────────────────────────────────────
    if wait_until_found(S.SEL_PREJOIN_SCREEN, 30) is None:
        status.log("Pre-join screen did not appear")
        return

    _prejoin_turn_off_camera()
    _prejoin_mute_mic()

    # Optional random delay before joining
    if 'random_delay' in rt.config:
        rd = rt.config['random_delay']
        if isinstance(rd, bool):
            delay = random.randrange(10, 31) if rd else 0
        else:
            delay = random.randrange(rd[0], rd[1] + 1)
        if delay > 0:
            status.log(f"Waiting {delay}s before joining…")
            time.sleep(delay)

    join_now = wait_until_found(S.SEL_PREJOIN_JOIN, 10)
    if join_now is None:
        return
    rt.browser.execute_script("arguments[0].click()", join_now)

    rt.current_meeting = meeting

    # Optional join message. new Teams uses a CKEditor message box, so the text
    # must be TYPED (send_keys) — setting textContent directly does not update
    # CKEditor's model, so the message would send empty / not at all.
    if rt.config.get("join_message"):
        time.sleep(3)
        try:
            if not _open_meeting_chat():
                status.log("Could not open the in-meeting chat")
            else:
                box = wait_until_found("div[data-tid='ckeditor']", 8, print_error=False)
                if box is None:
                    status.log("Could not find the chat message box")
                else:
                    box.click()
                    box.send_keys(rt.config["join_message"])
                    time.sleep(1)
                    # The send button is visually hidden until text is typed, so
                    # use wait_present (DOM presence) not wait_until_found (visibility).
                    # Meeting chat = 'newMessageCommands-send';
                    # existing chat  = 'sendMessageCommands-send'. Try both.
                    send_btn = (
                        wait_present("button[data-tid='newMessageCommands-send']", 4)
                        or wait_present("button[data-tid='sendMessageCommands-send']", 2)
                    )
                    if send_btn is not None:
                        rt.browser.execute_script("arguments[0].click()", send_btn)
                    else:
                        # Last resort: Ctrl+Enter (Teams sends on Ctrl+Enter, not plain Enter)
                        box.send_keys(Keys.CONTROL, Keys.ENTER)
                    status.log(f'Sent message: {rt.config["join_message"]}')
                    discord_notification("Sent message", rt.config["join_message"])
        except Exception as e:
            status.log(f"Failed to send join message: {e}")

    status.report("in_meeting", title=meeting.title, detail="Đang trong lớp")
    status.log(f"Joined meeting: {meeting.title}")
    discord_notification("Joined meeting", meeting.title)

    if rt.config.get('auto_leave_after_min', -1) > 0:
        rt.hangup_thread = Timer(rt.config['auto_leave_after_min'] * 60, hangup)
        rt.hangup_thread.start()


# Read directly off the roster BUTTON, no panel needed: Teams renders the live
# participant count either as trailing digits in its aria-label (e.g. "Người
# tham gia, 12" / "Show participants (12)") or as a small numeric badge next
# to the icon. Both are cheap DOM reads and survive minor UI shuffles better
# than any specific panel selector.
_JS_ROSTER_BADGE_COUNT = r"""
var btn = document.querySelector(arguments[0]);
if (!btn) return null;
var al = btn.getAttribute('aria-label') || '';
var m = al.match(/(\d+)\s*\)?\s*$/);
if (m) return parseInt(m[1], 10);
var badge = btn.querySelector('[data-tid$="badge"], .fui-Badge, [class*="badge" i]');
if (badge) {
  var t = (badge.textContent || '').trim();
  if (/^\d+$/.test(t)) return parseInt(t, 10);
}
return null;
"""

# Fallback once the People panel is open: sum any roster-section title counts
# (works if the old class names are still around) or, failing that, count the
# actual participant rows rendered in the panel — the row/list-item structure
# tends to outlive specific className/data-tid renames.
_JS_ROSTER_PANEL_COUNT = r"""
var total = 0, found = false;
document.querySelectorAll("calling-roster-section .roster-list-title, [class*='roster'] [class*='list-title' i]")
  .forEach(function(el){
    var al = el.getAttribute('aria-label') || el.textContent || '';
    var m = al.match(/\d+/);
    if (m) { total += parseInt(m[0], 10); found = true; }
  });
if (found) return total;
var rows = document.querySelectorAll(
  "[data-tid='roster-participant-list'] [role='listitem'], " +
  "[class*='roster' i] [role='listitem'], " +
  "[data-tid^='roster-list-item']");
return rows.length ? rows.length : null;
"""


def get_meeting_members():
    """
    Count participants currently in the meeting. Tries the roster button's
    own badge/aria-label first (fast, no UI disruption); if that fails, opens
    the People panel and reads it from there. Returns the count, or None if
    it could not be determined (the caller must treat None as "unknown", not
    "zero" — never trigger a leave decision on it).
    """
    # If the hangup button is gone, meeting ended
    if wait_until_found(S.SEL_HANGUP, 3, print_error=False) is None:
        rt.current_meeting = None
        status.log("No longer in any meeting")
        return None

    try:
        count = rt.browser.execute_script(_JS_ROSTER_BADGE_COUNT, S.SEL_ROSTER)
    except Exception:
        count = None
    if isinstance(count, int):
        return count

    # Slow path: open the People panel and read it from there.
    try:
        rt.browser.execute_script("document.querySelector(arguments[0]).click()", S.SEL_ROSTER)
    except Exception:
        status.log("Failed to open People panel")
        return None

    time.sleep(2)
    try:
        count = rt.browser.execute_script(_JS_ROSTER_PANEL_COUNT)
    except Exception:
        count = None

    # Close People panel (same button toggles it; try the "..." overflow menu
    # as a fallback if the toolbar collapsed it under there).
    try:
        rt.browser.execute_script("document.querySelector(arguments[0]).click()", S.SEL_ROSTER)
    except Exception:
        try:
            rt.browser.execute_script(
                "document.getElementById('callingButtons-showMoreBtn').click()")
            time.sleep(1)
            rt.browser.execute_script("document.querySelector(arguments[0]).click()", S.SEL_ROSTER)
        except Exception:
            pass

    return count if isinstance(count, int) else None


def hangup():
    if rt.current_meeting is None:
        return False

    try:
        hangup_btn = rt.browser.find_element(By.CSS_SELECTOR, S.SEL_HANGUP)
        hangup_btn.click()
        status.log(f"Left meeting: {rt.current_meeting.title}")
        discord_notification("Left Meeting", rt.current_meeting.title)
        rt.current_meeting = None
        status.report("idle", detail="Đã rời lớp")
        _cancel_auto_leave()
        return True
    except exceptions.NoSuchElementException:
        return False


def handle_leave_threshold(current_members, total):
    status.log(f"Số người hiện tại: {current_members} / Đỉnh điểm: {total}")
    # A count of 0 means the roster could not be read (we are in the call, so
    # there is always at least one person). Acting on it would divide by zero
    # in the percentage rule below, and would make every other rule fire and
    # drop us out of a class that is running perfectly well.
    if current_members <= 0 or total <= 0:
        return False

    leave_num  = rt.config.get("leave_threshold_number")
    leave_pct  = rt.config.get("leave_threshold_percentage")
    # Absolute minimum headcount: leave once the class drops below this many
    # people. Configurable (default 3); set to 0 (or negative) to disable —
    # this replaces what used to be a hardcoded "< 3" rule.
    min_members = rt.config.get("min_members", 3)
    try:
        min_members = int(min_members)
    except (TypeError, ValueError):
        min_members = 3

    if leave_num and int(leave_num) > 0:
        if (total - current_members) >= int(leave_num):
            status.log("Rời lớp: đã giảm quá số lượng tuyệt đối cấu hình")
            discord_notification("Left meeting, threshold triggered", rt.current_meeting.title)
            hangup()
            return True

    if leave_pct and 0 < int(leave_pct) <= 100:
        if (current_members / total) * 100 < int(leave_pct):
            status.log("Rời lớp: tỉ lệ người còn lại dưới ngưỡng cấu hình")
            discord_notification("Left meeting, threshold triggered", rt.current_meeting.title)
            hangup()
            return True

    if min_members > 0 and 0 < current_members < min_members:
        status.log(f"Rời lớp: chỉ còn {current_members} người (dưới mức tối thiểu {min_members})")
        discord_notification("Left meeting, below minimum members", rt.current_meeting.title)
        hangup()
        return True

    return False
