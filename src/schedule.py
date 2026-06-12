"""Main loop: discover → countdown → join early → stay → repeat."""

import sys
import time
from datetime import datetime, timedelta

import runtime as rt
import selectors_teams as S
import status
from browser import switch_to_teams_tab, wait_until_found
from joiner import (decide_meeting, get_meeting_members,
                    handle_leave_threshold, hangup, join_meeting)
from models import Meeting
from notify import discord_notification
from scanner import (_discover_calendar_events, discover_scheduled_meetings,
                     get_all_teams, get_meetings)


def _fmt_td(td):
    """Format a timedelta as HH:MM:SS (or 'N ngày HH:MM:SS')."""
    total = max(int(td.total_seconds()), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days} ngày {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _join_live_channel_meeting():
    """At class time, scan the channels for a meeting that is open right now and
    join it. Used for calendar-sourced class times (which carry no channel)."""
    rt.meetings = []
    teams = get_all_teams()
    if teams:
        get_meetings(teams)
    to_join = decide_meeting()
    if to_join is not None:
        join_meeting(to_join)
    return rt.current_meeting is not None


def _countdown_until(meeting, join_at, max_seconds):
    """Count down to join_at. Returns True when join_at is reached, or False once
    max_seconds elapse (caller should then re-scan).

    In a real terminal it updates ONE line in place via a carriage return. The
    line is kept short and padded to a fixed width so it overwrites cleanly
    without wrapping (which is what caused the per-second "spam") and without
    ANSI codes, so it works the same on macOS Terminal and Windows cmd/PowerShell.
    When output is redirected to a file it prints sparsely (every 20 s) instead."""
    status.report("countdown",
                  title=meeting.get("title") or "Buổi học",
                  join_at=join_at.timestamp(),
                  meeting_start=meeting["start"].timestamp(),
                  detail=f"Tự vào lúc {join_at:%H:%M}")
    end = time.time() + max_seconds
    title = (meeting.get("title") or "Buổi học")[:20]
    live = sys.stdout.isatty()
    last_log = 0.0
    ticks = 0
    while time.time() < end:
        status.check_stop()
        now = datetime.now()
        if now >= join_at:
            if live:
                sys.stdout.write("\n")
                sys.stdout.flush()
            return True
        # The countdown itself makes no browser calls, so check every ~10s that
        # Chrome is still open; if the user closed it, raise so the bot can stop
        # cleanly now instead of counting down to the end first.
        ticks += 1
        if ticks % 10 == 0:
            rt.browser.title  # raises InvalidSessionIdException if Chrome is gone
        remain = join_at - now
        if live:
            line = f"\r⏳ {title} · còn {_fmt_td(remain)} · vào {join_at:%H:%M}"
            sys.stdout.write(line.ljust(57))   # fixed width clears leftovers, no wrap
            sys.stdout.flush()
            time.sleep(1)
        else:
            if time.time() - last_log >= 20:
                print(f"[{now:%H:%M:%S}] {title} · còn {_fmt_td(remain)}"
                      f" · tự vào {join_at:%H:%M}")
                last_log = time.time()
            time.sleep(1)
    if live:
        sys.stdout.write("\n")
        sys.stdout.flush()
    return False


def _stay_until_meeting_ends():
    """Block while in a meeting; return when the call ends. Honors the optional
    'leave_if_last' / leave-threshold settings while in the call."""
    interval = max(int(rt.config.get('check_interval', 10) or 10), 3)
    rt.total_members = 0
    count = 0
    while rt.current_meeting is not None:
        status.check_stop()
        if wait_until_found(S.SEL_HANGUP, 5, print_error=False) is None:
            status.log("Đã rời lớp / lớp đã kết thúc.")
            rt.current_meeting = None
            return
        if rt.config.get('leave_if_last'):
            members = get_meeting_members()
            if rt.current_meeting is None:
                return
            if members and members > rt.total_members:
                rt.total_members = members
            if count % 5 == 0 and count > 0 and members is not None:
                if handle_leave_threshold(members, rt.total_members):
                    return
        count += 1
        status.sleep_checked(interval)


def run_schedule_loop():
    """Main loop for channel-based classes: discover scheduled meetings, show a
    countdown to the next one, then auto-join it `join_before_min` minutes early
    (retrying until the meeting is actually open)."""
    join_before = max(int(rt.config.get('join_before_min', 2) or 0), 0)
    rescan_seconds = max(int(rt.config.get('rescan_min', 10) or 10), 1) * 60
    status.log(f"Chế độ đếm ngược: tự vào lớp sớm {join_before} phút trước giờ bắt đầu.")

    # Sessions already attended (or attempted), so we don't keep re-joining the
    # class we just left. Lives in rt so it survives a browser restart.
    def _key(m):
        return (m.get("channel_id") or m.get("title"), m["start"].isoformat())

    while True:
        status.check_stop()
        status.report("scanning", detail="Đang dò lịch học…")
        status.log("Đang dò lịch học… chờ chút")
        schedule = []
        if rt.mode != 3:   # mode 1 (cả hai) / 2 (chỉ kênh) → quét banner trong kênh
            try:
                schedule += discover_scheduled_meetings()
            except status.BotStopped:
                raise
            except Exception as e:
                status.log(f"Lỗi khi dò kênh: {e}")
        if rt.mode != 2:   # mode 1 (cả hai) / 3 (chỉ lịch) → đọc sự kiện trên Lịch Outlook
            try:
                schedule += _discover_calendar_events()
            except status.BotStopped:
                raise
            except Exception as e:
                status.log(f"Lỗi khi đọc lịch: {e}")

        # Khử trùng theo giờ bắt đầu; ưu tiên mục có kênh (vào lớp chính xác hơn).
        by_start = {}
        for m in schedule:
            k = m["start"].isoformat()
            if k not in by_start or (m.get("channel_id") and not by_start[k].get("channel_id")):
                by_start[k] = m
        schedule = list(by_start.values())

        status.report(schedule=[
            {"title": m["title"], "start": m["start"].timestamp()}
            for m in sorted(schedule, key=lambda m: m["start"])])

        now = datetime.now()
        # Keep upcoming meetings, plus ones that started within the last 3h (a
        # class may still be ongoing). Channels also keep past sessions — ignore
        # those, and ignore any session we have already handled this run.
        upcoming = sorted(
            (m for m in schedule
             if m["start"] >= now - timedelta(hours=3) and _key(m) not in rt.handled),
            key=lambda m: m["start"])

        if not upcoming:
            mins = rescan_seconds // 60
            status.report("idle", detail=f"Chưa thấy buổi học sắp tới — quét lại sau {mins} phút")
            status.log(f"Chưa thấy buổi học sắp tới. Quét lại sau {mins} phút.")
            status.sleep_checked(rescan_seconds)
            continue

        nxt = upcoming[0]
        join_at = nxt["start"] - timedelta(minutes=join_before)
        status.log(f"Buổi kế tiếp: {nxt['title']} — bắt đầu {nxt['start']:%H:%M %d/%m}")

        # Count down (re-scanning periodically in case the schedule changes).
        if not _countdown_until(nxt, join_at, rescan_seconds):
            continue  # window elapsed without reaching join time → re-scan

        # ── Time to join ───────────────────────────────────────────────────
        rt.handled.add(_key(nxt))  # don't re-pick this session after we leave it
        status.report("joining", title=nxt["title"], detail="Đang vào lớp…")
        status.log(f"⏰ Tới giờ vào lớp: {nxt['title']}")
        discord_notification("Tới giờ vào lớp", nxt["title"])

        # Retry until joined or 15 min past the scheduled start (the teacher may
        # open the meeting a little late). A channel-sourced item knows its exact
        # channel; a calendar-sourced item only knows the time, so we scan the
        # channels for whatever class is open right now.
        deadline = nxt["start"] + timedelta(minutes=15)
        while datetime.now() < deadline and rt.current_meeting is None:
            status.check_stop()
            if nxt.get("channel_id"):
                # Channel-sourced: navigate to that channel and click its Join.
                join_meeting(Meeting(
                    m_id=f"channel:{nxt['channel_id']}",
                    time_started=int(time.time()),
                    title=nxt["title"],
                    calendar_meeting=False,
                    channel_id=nxt["channel_id"],
                    team_id=nxt["team_id"],
                ))
            else:
                # Calendar-sourced: open the meeting ON THE CALENDAR and click
                # "Tham gia" (the user's classes are Teams meetings on the calendar).
                join_meeting(Meeting(
                    m_id=f"calendar:{nxt['title']}@{nxt['start'].isoformat()}",
                    time_started=int(time.time()),
                    title=nxt["title"],
                    calendar_meeting=True,
                ))
            if rt.current_meeting is not None:
                break
            status.log("Lớp chưa mở để vào — thử lại sau 20 giây…")
            status.sleep_checked(20)

        if rt.current_meeting is None:
            status.log("Không vào được lớp (quá giờ). Tìm buổi tiếp theo.")
            continue

        _stay_until_meeting_ends()
