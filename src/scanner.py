"""Discover classes: channel meeting banners + Outlook calendar events."""

import re
import time
from datetime import datetime

from selenium.common import exceptions
from selenium.webdriver.common.by import By

import runtime as rt
import selectors_teams as S
import status
from browser import (switch_to_calendar_tab, switch_to_teams_tab,
                     wait_until_found)
from models import Channel, Meeting, Team


def get_all_teams():
    """Return a flat list of Team objects from the Teams grid view."""
    switch_to_teams_tab()
    if wait_until_found(S.SEL_TEAMS_GRID, 10, print_error=False) is None:
        status.log("Teams grid not found — is the Teams tab showing grid view?")
        return []

    cards = rt.browser.find_elements(By.CSS_SELECTOR, S.SEL_TEAM_CARD)
    teams = []
    for card in cards:
        tid_attr = card.get_attribute("data-tid") or ""
        thread_id = tid_attr.replace("-team-card", "")
        if not thread_id:
            continue
        aria = card.get_attribute("aria-label") or ""
        # aria-label is "TEAM_NAME Team X of Y" (EN) or "... Nhóm X của Y" (VI)
        # — strip the trailing position suffix in either language.
        name = re.sub(r'\s+(Team|Nhóm)\s+\d+\s+(of|của)\s+\d+\s*$', '', aria).strip()
        if not name:
            name = thread_id
        teams.append(Team(name, thread_id))
    return teams


def _get_channels_from_sidebar(team):
    """
    Read the channel sidebar after navigating into a team.
    Returns list of Channel objects and updates channel_to_team mapping.
    """
    items = rt.browser.find_elements(By.CSS_SELECTOR, S.SEL_CHANNEL_ITEM)
    channels = []
    for item in items:
        sid = item.get_attribute("data-sid") or ""
        if not sid.startswith("channel-shown-"):
            continue
        c_id = sid.replace("channel-shown-", "")
        try:
            text_el = item.find_element(
                By.CSS_SELECTOR, "[data-tid^='channel-list-item-text-']")
            name = text_el.text.strip() or c_id
        except exceptions.NoSuchElementException:
            name = c_id
        channels.append(Channel(name, c_id))
        rt.channel_to_team[c_id] = team.t_id
    return channels


def get_meetings(teams):
    """
    For each team, navigate to it, collect channels, then check each channel
    for an active/upcoming meeting join button.
    """
    for team in teams:
        # Navigate to team card
        switch_to_teams_tab()
        card = wait_until_found(
            f"[data-tid='{team.t_id}-team-card']", 5, print_error=False)
        if card is None:
            continue
        rt.browser.execute_script("arguments[0].click()", card)
        time.sleep(2)

        # Collect channels from sidebar (element refs go stale after clicks)
        channels = _get_channels_from_sidebar(team)
        team.channels = channels
        team.check_blacklist()

        for ch in team.channels:
            if ch.blacklisted:
                continue

            # Navigate to channel
            ch_btn = wait_until_found(
                f"[data-tid='channel-list-item-text-{ch.c_id}']",
                3, print_error=False)
            if ch_btn is None:
                continue
            try:
                rt.browser.execute_script("arguments[0].click()", ch_btn)
                time.sleep(2)
            except Exception:
                continue

            # Check for an active meeting join button
            if wait_until_found(S.SEL_CH_JOIN_BTN, 3, print_error=False) is None:
                continue

            m_id = f"channel:{ch.c_id}"
            if m_id in rt.already_joined_ids:
                continue

            title = f"{team.name} → {ch.name}"
            try:
                banner = rt.browser.find_element(By.CSS_SELECTOR, S.SEL_MEETING_BANNER)
                aria = banner.get_attribute("aria-label") or ""
                # "Scheduled meeting. TITLE. DATE..."
                parts = [p.strip() for p in aria.split(".") if p.strip()]
                if len(parts) >= 2:
                    title = parts[1]
            except exceptions.NoSuchElementException:
                pass

            rt.meetings.append(Meeting(
                m_id=m_id,
                time_started=int(time.time()),
                title=title,
                calendar_meeting=False,
                channel_id=ch.c_id,
                team_id=team.t_id,
            ))
            ch.has_meeting = True

    # Return to teams grid after full scan
    switch_to_teams_tab()


def get_calendar_meetings():
    """Scan the Outlook calendar (embedded iframe) for Teams meeting events."""
    switch_to_calendar_tab()
    time.sleep(4)

    iframe = wait_until_found(S.SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        status.log("Calendar iframe not found (is the Calendar tab open?)")
        return

    # The Outlook calendar inside the iframe renders its events asynchronously,
    # so poll until events appear (or the calendar is loaded with none).
    rt.browser.switch_to.frame(iframe)
    labels = []
    try:
        deadline = time.time() + 18
        ready_since = None
        while time.time() < deadline:
            try:
                n = rt.browser.execute_script(
                    'return document.querySelectorAll(\'button,[role="button"]\').length;') or 0
                labels = rt.browser.execute_script(S._JS_CAL_EVENTS) or []
            except Exception:
                n, labels = 0, []
            if labels:
                break
            if n > 25:               # OWA calendar grid has rendered
                if ready_since is None:
                    ready_since = time.time()
                elif time.time() - ready_since > 4:   # loaded, still no events
                    break
            time.sleep(1.5)
    finally:
        rt.browser.switch_to.default_content()

    for label in labels:
        # aria-label looks like "TITLE, 12:30 AM to 1:00 AM, Monday, ... , Microsoft Teams ..."
        title = label.split(",")[0].strip() or "Calendar meeting"
        m_id = "calendar:" + label
        if m_id in rt.already_joined_ids:
            continue
        mtg = Meeting(
            m_id=m_id,
            time_started=int(time.time()),
            title=title,
            calendar_meeting=True,
        )
        mtg.cal_label = label
        rt.meetings.append(mtg)


# Channel meeting banner aria-label (Vietnamese) looks like:
#   "Cuộc họp đã lên lịch. <TÊN>. Thứ Hai, 9 tháng 2, 2026 12:30. Nhấn enter…"
# The schedule datetime is the "<day> tháng <month>, <year> <H>:<MM>" part. The
# regex anchors on "tháng" + a trailing H:MM so it never matches a date that may
# be embedded in the title (e.g. "Ngày 03.02.2026" / "Lúc 07h15").
_BANNER_DT_RE = re.compile(r'(\d{1,2})\s+tháng\s+(\d{1,2}),\s*(\d{4})\s+(\d{1,2}):(\d{2})')


def _parse_banner_time(aria):
    """Return a datetime for a scheduled-meeting banner aria-label, or None."""
    m = _BANNER_DT_RE.search(aria or "")
    if not m:
        return None
    day, month, year, hour, minute = (int(x) for x in m.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def discover_scheduled_meetings():
    """Scan every (non-blacklisted) channel of every team and parse the start
    time of any scheduled-meeting banner found. Returns a de-duplicated list of
    dicts: {start, title, team_id, channel_id}."""
    found = {}
    teams = get_all_teams()
    for team in teams:
        switch_to_teams_tab()
        card = wait_until_found(
            f"[data-tid='{team.t_id}-team-card']", 5, print_error=False)
        if card is None:
            continue
        try:
            rt.browser.execute_script("arguments[0].click()", card)
        except Exception:
            continue
        time.sleep(2)

        team.channels = _get_channels_from_sidebar(team)
        team.check_blacklist()

        for ch in team.channels:
            if ch.blacklisted:
                continue
            ch_btn = wait_until_found(
                f"[data-tid='channel-list-item-text-{ch.c_id}']", 3, print_error=False)
            if ch_btn is None:
                continue
            try:
                rt.browser.execute_script("arguments[0].click()", ch_btn)
                time.sleep(1.5)
            except Exception:
                continue

            for banner in rt.browser.find_elements(By.CSS_SELECTOR, S.SEL_MEETING_BANNER):
                try:
                    aria = banner.get_attribute("aria-label") or ""
                except Exception:
                    continue
                start = _parse_banner_time(aria)
                if start is None:
                    continue
                key = (ch.c_id, start.isoformat())
                found[key] = {
                    "start": start,
                    "title": f"{team.name} → {ch.name}",
                    "team_id": team.t_id,
                    "channel_id": ch.c_id,
                }

    switch_to_teams_tab()
    return list(found.values())


# Outlook-calendar event aria-labels (Vietnamese) look like:
#   "môn toán, 5:02 CH đến 5:32 CH, Thứ Hai, Tháng 6 01, 2026, Busy"
# Note the calendar differs from the channel banner: the time is 12-hour with
# SA (AM) / CH (PM), and the date is "Tháng <month> <day>, <year>" (month first).
_CAL_TIME_RE = re.compile(r'(\d{1,2}):(\d{2})\s*(SA|CH)')
_CAL_DATE_RE = re.compile(r'Tháng\s+(\d{1,2})\s+(\d{1,2}),\s*(\d{4})')


def _parse_calendar_time(aria):
    """Return the start datetime of an Outlook-calendar event aria-label, or None."""
    tm = _CAL_TIME_RE.search(aria or "")
    dm = _CAL_DATE_RE.search(aria or "")
    if not tm or not dm:
        return None
    hour, minute, ampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
    if ampm == "CH" and hour != 12:      # PM
        hour += 12
    elif ampm == "SA" and hour == 12:    # 12 AM = midnight
        hour = 0
    month, day, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _discover_calendar_events():
    """Read class times the user put on the Outlook calendar. Returns
    [{start, title, source:'calendar'}] (no channel — these are time markers;
    the actual class is joined via its channel)."""
    out = []
    switch_to_calendar_tab()
    time.sleep(3)
    iframe = wait_until_found(S.SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        return out

    rt.browser.switch_to.frame(iframe)
    labels = []
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                n = rt.browser.execute_script(
                    'return document.querySelectorAll(\'button,[role="button"]\').length;') or 0
                labels = rt.browser.execute_script(S._CAL_EVENTS_JS) or []
            except Exception:
                n, labels = 0, []
            if n > 30 and labels:
                break
            time.sleep(1.5)
    finally:
        rt.browser.switch_to.default_content()

    for al in labels:
        low = al.lower()
        if any(s in low for s in S._CAL_SKIP):
            continue
        start = _parse_calendar_time(al)
        if start is None:
            continue
        title = al.split(",")[0].strip()
        # Skip time-block / "working hours" / selection markers: those have no
        # real title (their first segment is itself a time, e.g. "6:00 CH đến …").
        if not title or _CAL_TIME_RE.match(title):
            continue
        out.append({"start": start, "title": title, "source": "calendar"})
    return out
