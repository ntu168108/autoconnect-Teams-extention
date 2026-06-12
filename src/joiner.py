"""Join a class: open it (channel or calendar), pre-join (cam/mic off),
send the optional join message, leave, and count participants."""

import random
import time
from threading import Timer

from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import runtime as rt
import selectors_teams as S
import status
from browser import (switch_to_calendar_tab, switch_to_teams_tab,
                     wait_present, wait_until_found)
from notify import discord_notification


def decide_meeting():
    rt.meetings = [m for m in rt.meetings if not m.calendar_blacklisted]
    if not rt.meetings:
        return None

    rt.meetings.sort(key=lambda x: x.time_started, reverse=True)
    newest_time = rt.meetings[0].time_started

    newest = [m for m in rt.meetings if m.time_started >= newest_time]

    candidate = newest[0]
    if (rt.current_meeting is None
            or candidate.time_started > rt.current_meeting.time_started
            or candidate.m_id != rt.current_meeting.m_id) \
            and candidate.m_id not in rt.already_joined_ids:
        return candidate
    return None


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


def join_meeting(meeting):
    hangup()

    # ── Reach the pre-join screen ──────────────────────────────────────────
    if meeting.calendar_meeting:
        if not _open_calendar_meeting(meeting):
            return
        # _open_calendar_meeting already clicked Join inside the iframe.
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
    rt.already_joined_ids.append(meeting.m_id)

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


def get_meeting_members():
    """
    Count participants in the current meeting via the People panel.
    Returns total count, or None if unavailable.

    NOTE: The exact roster-panel selectors for new Teams have not been
    confirmed yet (a 'trong-hop' DOM dump with People panel open is needed).
    Currently falls back to None so the main loop still runs.
    """
    # If the hangup button is gone, meeting ended
    if wait_until_found(S.SEL_HANGUP, 3, print_error=False) is None:
        rt.current_meeting = None
        status.log("No longer in any meeting")
        return None

    try:
        rt.browser.execute_script("document.getElementById('roster-button').click()")
    except exceptions.JavascriptException:
        status.log("Failed to open People panel")
        return None

    time.sleep(2)

    # Try old-style selector first (might still match in new Teams)
    participants_elem = wait_until_found(
        "calling-roster-section[section-key='participantsInCall'] .roster-list-title",
        2, print_error=False)
    attendees_elem = wait_until_found(
        "calling-roster-section[section-key='attendeesInMeeting'] .roster-list-title",
        2, print_error=False)

    count = None
    if participants_elem is not None or attendees_elem is not None:
        participants = ([int(s) for s in (participants_elem.get_attribute("aria-label") or "").split() if s.isdigit()]
                        if participants_elem else [0])
        attendees    = ([int(s) for s in (attendees_elem.get_attribute("aria-label") or "").split() if s.isdigit()]
                        if attendees_elem else [0])
        count = sum(participants + attendees)

    # Close People panel
    try:
        rt.browser.execute_script("document.getElementById('roster-button').click()")
    except exceptions.JavascriptException:
        try:
            rt.browser.execute_script(
                "document.getElementById('callingButtons-showMoreBtn').click()")
            time.sleep(1)
            rt.browser.execute_script("document.getElementById('roster-button').click()")
        except exceptions.JavascriptException:
            pass

    return count


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
        if rt.hangup_thread:
            rt.hangup_thread.cancel()
        return True
    except exceptions.NoSuchElementException:
        return False


def handle_leave_threshold(current_members, total):
    status.log(f"Current members: {current_members} / Peak: {total}")
    leave_num  = rt.config.get("leave_threshold_number")
    leave_pct  = rt.config.get("leave_threshold_percentage")

    if leave_num and int(leave_num) > 0:
        if (total - current_members) >= int(leave_num):
            status.log("Leave threshold (absolute) triggered")
            discord_notification("Left meeting, threshold triggered", rt.current_meeting.title)
            hangup()
            return True

    if leave_pct and 0 < int(leave_pct) <= 100:
        if (current_members / total) * 100 < int(leave_pct):
            status.log("Leave threshold (percentage) triggered")
            discord_notification("Left meeting, threshold triggered", rt.current_meeting.title)
            hangup()
            return True

    if 0 < current_members < 3:
        status.log("Last person in meeting")
        discord_notification("Left meeting, last member", rt.current_meeting.title)
        hangup()
        return True

    return False
