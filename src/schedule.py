"""Main loop: discover → countdown → join early → stay → repeat."""

import sys
import time
from datetime import datetime, timedelta

import runtime as rt
import selectors_teams as S
import status
from browser import browser_dead, wait_until_found
from joiner import (get_meeting_members, handle_leave_threshold, hangup,
                    join_meeting, leave_reason)
from models import Meeting
from notify import discord_notification
from scanner import _discover_calendar_events, discover_scheduled_meetings


def _short_err(e):
    """First line of an exception message — selenium appends a chromedriver
    stacktrace that is useless noise in the user-facing log."""
    return str(e).split("\n", 1)[0].strip() or type(e).__name__


def _fmt_td(td):
    """Format a timedelta as HH:MM:SS (or 'N ngày HH:MM:SS')."""
    total = max(int(td.total_seconds()), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days} ngày {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _sleep_or_join(seconds):
    """status.sleep_checked, but returns as soon as the user clicks 'Vào lớp
    ngay' (or 'Rời lớp') on the dashboard instead of sleeping out the full
    interval."""
    end = time.time() + seconds
    while time.time() < end:
        if rt.join_request is not None or rt.leave_request:
            return
        status.sleep_checked(min(1.0, max(end - time.time(), 0)))


def _key(m):
    """Identity of a class session, used to remember what we already sat in."""
    return (m.get("channel_id") or m.get("title"), m["start"].isoformat())


def _pick_order(schedule, now):
    """Order the scanned classes by what the bot should go to next.

    A class already in progress comes first — the one that started most
    recently, i.e. the class happening right now — then the classes still to
    come, soonest first. Sorting purely by start time would put a class that
    began nearly three hours ago (and has since ended) ahead of the one
    actually running.

    A class is dropped once it has finished. The calendar API gives a real end
    time; the scraped path does not, so those fall back to assuming a class
    runs no longer than `stale_after_hours`.
    """
    stale_after = timedelta(hours=max(
        int(rt.config.get("stale_after_hours", 3) or 3), 1))

    live, later = [], []
    for m in schedule:
        if _key(m) in rt.handled:
            continue
        end = m.get("end")
        if m["start"] > now:
            later.append(m)
        elif (end > now) if end is not None else (m["start"] >= now - stale_after):
            live.append(m)

    live.sort(key=lambda m: m["start"], reverse=True)   # nearest to now first
    later.sort(key=lambda m: m["start"])
    return live + later


def _take_join_request():
    """Pop the class the user clicked 'Vào lớp ngay' on, if any. The dashboard
    resolves the click to the class itself, so this is never a stale index."""
    entry, rt.join_request = rt.join_request, None
    if entry is not None and _key(entry) in rt.handled:
        # Already attended this run — a click that arrived while we were
        # joining it would otherwise send us back to a class that has ended,
        # burning the join window that belongs to the next one.
        status.log(f"Bỏ qua yêu cầu vào lại buổi đã học: {entry['title']}")
        return None
    return entry


def _countdown_until(meeting, join_at, max_seconds):
    """Count down to join_at. Returns True when join_at is reached, or False
    once max_seconds elapse / the user asked for a specific class on the
    dashboard (caller should then re-scan or honour that request).

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
        if now >= join_at or rt.join_request is not None:
            if live:
                sys.stdout.write("\n")
                sys.stdout.flush()
            # A dashboard click is not a time-based join — report it as "not
            # reached" so that if the click turns out to be stale the caller
            # rescans instead of joining this class ahead of its time.
            return rt.join_request is None
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


def _switch_at(entry, join_before):
    """When to leave `entry` for the class after it, or None if there is none.

    That is the next class's own join time, except that an event overlapping
    this one (a meeting in the middle of it, say) waits for this class's
    scheduled end rather than cutting it short. Reads the scan taken just
    before joining: scanning again from inside the call would navigate away
    from it."""
    later = [m for m in rt.schedule
             if m["start"] > entry["start"] and _key(m) not in rt.handled]
    if not later:
        return None
    nxt = min(later, key=lambda m: m["start"])
    leave = max(nxt["start"], entry.get("end") or nxt["start"])
    return leave - timedelta(minutes=join_before)


# What _stay_until_meeting_ends reports when the call went away on its own —
# a network drop, being removed, or the teacher ending the class — rather
# than because the bot hung up.
DROPPED = "dropped"


def _leave_at(entry, join_before):
    """(when, why) to leave `entry` of our own accord, or (None, None)."""
    at = _switch_at(entry, join_before)
    why = "Tới giờ vào buổi học kế tiếp — rời lớp hiện tại."
    end = entry.get("end")
    if _key(entry) in rt.rejoins and end is not None and (at is None or end < at):
        # A re-join may have restarted a meeting the teacher had ended early,
        # and nothing would ever end that one: stop at the class's own end.
        at, why = end, "Hết giờ buổi học — rời lớp."
    return at, why


def _leave_now(why):
    """Hang up on purpose, and make sure the loop can move on either way."""
    status.log(why)
    if not hangup():
        # Joining the next class navigates away from this call anyway; a
        # stale current_meeting would stop the join loop from even trying.
        rt.left_by_bot = True
        rt.current_meeting = None


def _stay_until_meeting_ends(entry=None, join_before=0):
    """Block while in a meeting. Returns DROPPED if the call ended on its own,
    None if we left it: a leave rule fired, it was time for the next class,
    or the user asked from the dashboard.

    Without the next-class check a call the lecturer never ends — they just
    walk off, and a few students linger — kept the bot in the old class
    straight through the next one."""
    interval = max(int(rt.config.get('check_interval', 10) or 10), 3)
    # How many readings in a row must agree before a leave rule acts. One
    # reading taken while the roster re-renders or the call reconnects can
    # come back far too low, and acting on it drops a class that is fine.
    confirm = max(int(rt.config.get('leave_confirm_checks', 3) or 3), 1)
    leave_at, leave_why = (_leave_at(entry, join_before) if entry is not None
                           else (None, None))
    key = _key(entry) if entry is not None else None
    # Back in after a drop, the class has already gathered: keep its peak, so
    # coming back to an emptied room reads as the class having emptied.
    rt.total_members = rt.peaks.get(key, 0)
    rt.left_by_bot = False
    rt.leave_request = False       # a click meant for the previous class
    last_members = None
    streak = 0
    missing = 0
    while rt.current_meeting is not None:
        status.check_stop()
        if wait_until_found(S.SEL_HANGUP, 5, print_error=False) is None:
            # Missing once is not enough: a reconnect or a re-render can hide
            # the toolbar for a moment, and calling that the end loses the class.
            missing += 1
            if missing < 2 and not rt.left_by_bot:
                continue
            rt.current_meeting = None
            if rt.left_by_bot:        # we hung up (the auto-leave timer), or meant to
                return None
            status.log("Đã rời lớp / lớp đã kết thúc.")
            return DROPPED
        missing = 0
        if rt.leave_request:
            rt.leave_request = False
            _leave_now("Rời lớp theo yêu cầu từ bảng theo dõi.")
            return None
        if rt.join_request is not None:
            _leave_now("Rời lớp hiện tại để vào buổi bạn vừa chọn trên bảng theo dõi.")
            return None
        if leave_at is not None and datetime.now() >= leave_at:
            _leave_now(leave_why)
            return None
        if rt.config.get('leave_if_last'):
            members = get_meeting_members()
            if rt.current_meeting is None:     # the auto-leave timer hung up
                return None
            # None is "could not read", not a headcount: it neither confirms
            # nor clears a pending leave.
            if members is not None:
                rt.total_members = max(rt.total_members, members)
                if key is not None:
                    rt.peaks[key] = rt.total_members
                if members != last_members:
                    status.log(f"Số người hiện tại: {members} / "
                               f"Đỉnh điểm: {rt.total_members}")
                    last_members = members
                streak = streak + 1 if leave_reason(members, rt.total_members) else 0
                if streak >= confirm:
                    # From here on we mean to leave. If the hang-up does not
                    # go through we keep watching and retry, and should the
                    # call vanish meanwhile, that is our leave, not a drop to
                    # re-join — going back in would undo the rule.
                    rt.left_by_bot = True
                    if handle_leave_threshold(members, rt.total_members):
                        return None
        _sleep_or_join(interval)
    return None


def _may_rejoin(entry, now):
    """Whether to go back into a class whose call dropped on its own.

    Only while the class still has a good while left by its scheduled end —
    known for classes read through the calendar API — and only a couple of
    times: a teacher ending class early makes the call vanish the same way,
    and each re-join then just restarts an empty meeting."""
    end = entry.get("end")
    if end is None or now >= end - timedelta(minutes=10):
        return False
    try:
        limit = int(rt.config.get("max_rejoins", 2))
    except (TypeError, ValueError):
        limit = 2
    return rt.rejoins.get(_key(entry), 0) < limit


def _rearm_after_drop(entry, outcome, now):
    """Put a class whose call dropped mid-class back up for joining. Returns
    True if it will be re-joined.

    Marking a class handled up front is what keeps us from re-joining one we
    chose to leave; a call that dropped out from under us is not that, so the
    next pass may pick it up again — it is still running, so it comes first."""
    if outcome != DROPPED or not _may_rejoin(entry, now):
        return False
    k = _key(entry)
    rt.rejoins[k] = rt.rejoins.get(k, 0) + 1
    rt.handled.discard(k)
    status.report("idle", detail="Bị rớt khỏi lớp — đang vào lại…")
    status.log(f"Bị rớt khỏi lớp khi buổi học chưa hết giờ — vào lại "
               f"(lần {rt.rejoins[k]}).")
    discord_notification("Bị rớt khỏi lớp, đang vào lại", entry["title"])
    return True


def run_schedule_loop():
    """Main loop for channel-based classes: discover scheduled meetings, show a
    countdown to the next one, then auto-join it `join_before_min` minutes early
    (retrying until the meeting is actually open)."""
    join_before = max(int(rt.config.get('join_before_min', 2) or 0), 0)
    rescan_seconds = max(int(rt.config.get('rescan_min', 10) or 10), 1) * 60
    status.log(f"Chế độ đếm ngược: tự vào lớp sớm {join_before} phút trước giờ bắt đầu.")

    # Sessions already attended (or attempted) are tracked in rt.handled (see
    # _key), so we don't keep re-joining the class we just left. It lives in rt
    # so it survives a browser restart.
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
                if browser_dead(e):
                    raise
                status.log(f"Lỗi khi dò kênh: {_short_err(e)}")
        if rt.mode != 2:   # mode 1 (cả hai) / 3 (chỉ lịch) → đọc sự kiện trên Lịch Outlook
            try:
                schedule += _discover_calendar_events()
            except status.BotStopped:
                raise
            except Exception as e:
                if browser_dead(e):
                    raise
                status.log(f"Lỗi khi đọc lịch: {_short_err(e)}")

        # Khử trùng theo giờ bắt đầu; ưu tiên mục có kênh (vào lớp chính xác hơn).
        by_start = {}
        for m in schedule:
            k = m["start"].isoformat()
            if k not in by_start or (m.get("channel_id") and not by_start[k].get("channel_id")):
                by_start[k] = m
        schedule = list(by_start.values())

        rt.schedule = sorted(schedule, key=lambda m: m["start"])
        status.report(schedule=[
            {"idx": i, "title": m["title"], "start": m["start"].timestamp(),
             "end": m["end"].timestamp() if m.get("end") else None}
            for i, m in enumerate(rt.schedule)])

        now = datetime.now()
        upcoming = _pick_order(schedule, now)

        if not upcoming:
            mins = rescan_seconds // 60
            status.report("idle", detail=f"Chưa thấy buổi học sắp tới — quét lại sau {mins} phút")
            status.log(f"Chưa thấy buổi học sắp tới. Quét lại sau {mins} phút.")
            _sleep_or_join(rescan_seconds)
            manual = _take_join_request()
            if manual is None:
                continue
            nxt = manual
        else:
            nxt = upcoming[0]
            join_at = nxt["start"] - timedelta(minutes=join_before)
            status.log(f"Buổi kế tiếp: {nxt['title']} — bắt đầu {nxt['start']:%H:%M %d/%m}")

            # Count down (re-scanning periodically in case the schedule changes).
            reached = _countdown_until(nxt, join_at, rescan_seconds)
            manual = _take_join_request()
            if manual is not None:
                nxt = manual
            elif not reached:
                continue  # window elapsed without reaching join time → re-scan

        # ── Time to join ───────────────────────────────────────────────────
        rt.handled.add(_key(nxt))  # don't re-pick this session after we leave it
        rt.current_entry = nxt
        status.report("joining", title=nxt["title"], detail="Đang vào lớp…")
        if manual is not None:
            status.log(f"▶ Vào lớp theo yêu cầu từ bảng theo dõi: {nxt['title']}")
            discord_notification("Vào lớp theo yêu cầu", nxt["title"])
        else:
            status.log(f"⏰ Tới giờ vào lớp: {nxt['title']}")
            discord_notification("Tới giờ vào lớp", nxt["title"])

        # Retry until joined or 15 min past the scheduled start (the teacher may
        # open the meeting a little late). A channel-sourced item knows its exact
        # channel; a calendar-sourced item only knows the time, so we scan the
        # channels for whatever class is open right now.
        #
        # Count those 15 minutes from now for a class that has already started
        # — one the user clicked, or one already in progress that we are only
        # now catching up with. Measuring from its start would put the deadline
        # in the past, so the retry loop below would not run even once and the
        # class would be skipped outright. Never keep trying past the end of
        # the class, when we know it.
        started_already = manual is not None or nxt["start"] <= datetime.now()
        deadline = (datetime.now() if started_already else nxt["start"]) \
            + timedelta(minutes=15)
        if nxt.get("end") is not None:
            deadline = min(deadline, nxt["end"])
        # rt.current_meeting only goes non-None once we are actually in the
        # call, which is a good half-minute into join_meeting(); the flag marks
        # the whole attempt so the dashboard can refuse clicks meanwhile.
        rt.joining = True
        try:
            while datetime.now() < deadline and rt.current_meeting is None:
                status.check_stop()
                # Teams re-renders constantly, so an element located a moment
                # ago can be stale by the time we click it. Swallow that the
                # same way the scans above do: retry on the next pass rather
                # than letting one hiccup end the whole run.
                try:
                    if nxt.get("channel_id"):
                        # Channel-sourced: navigate to that channel and click its Join.
                        join_meeting(Meeting(
                            m_id=f"channel:{nxt['channel_id']}",
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
                            title=nxt["title"],
                            calendar_meeting=True,
                            thread_id=nxt.get("cid"),
                            reply_id=nxt.get("rid"),
                        ))
                except status.BotStopped:
                    raise
                except Exception as e:
                    if browser_dead(e):
                        raise
                    status.log(f"Lỗi khi vào lớp: {_short_err(e)}")
                if rt.current_meeting is not None:
                    break
                status.log("Lớp chưa mở để vào — thử lại sau 20 giây…")
                status.sleep_checked(20)
        finally:
            rt.joining = False

        if rt.current_meeting is None:
            rt.current_entry = None
            status.log("Không vào được lớp (quá giờ). Tìm buổi tiếp theo.")
            continue

        outcome = None
        try:
            outcome = _stay_until_meeting_ends(nxt, join_before)
        except status.BotStopped:
            raise
        except Exception as e:
            if browser_dead(e):
                raise
            # Losing track of the call is not a reason to end the run: drop the
            # meeting and go back to scanning for the next class.
            status.log(f"Lỗi khi đang trong lớp: {_short_err(e)}")
            rt.current_meeting = None
        finally:
            rt.current_entry = None

        if _rearm_after_drop(nxt, outcome, datetime.now()):
            continue
        status.report("idle", detail="Đã rời lớp — đang kiểm tra buổi học tiếp theo…")
        status.log("Đã rời lớp. Đang kiểm tra lịch xem có buổi học tiếp theo không…")
