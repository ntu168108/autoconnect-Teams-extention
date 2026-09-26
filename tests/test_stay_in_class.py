"""What the bot does while it sits in a class.

Two things went wrong here over a long unattended run:

* The "leave when the class empties" rule judged a class that had not even
  gathered yet. Joining a couple of minutes early means being alone or with
  the teacher, so the headcount was below the minimum and the bot left —
  and since the class was already marked handled, it never went back.
* Nothing in the loop looked at the schedule. A call the lecturer never ends
  kept the bot in the old class straight through the start of the next one.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import joiner
import runtime as rt
import schedule as sched
import status

START = datetime(2026, 9, 21, 7, 0)
INTERVAL = 10


class _Meeting:
    title = "Lập trình Python"


class _Class:
    """Scripted class: headcount per check, and whether the call is still up.
    Also drives a fake clock that advances one check_interval per sleep."""

    def __init__(self, monkeypatch, counts, in_call=lambda i: True,
                 hangup_works=True, now=START - timedelta(minutes=2),
                 on_sleep=None):
        self.counts = counts
        self.in_call = in_call
        self.hangup_works = hangup_works
        self.on_sleep = on_sleep
        self.i = 0
        self.now = now
        self.left_at = None
        self.checks = 0
        clock = self

        class _Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now

        monkeypatch.setattr(sched, "datetime", _Clock)
        monkeypatch.setattr(sched, "wait_until_found", self._hangup_button)
        monkeypatch.setattr(sched, "get_meeting_members", self._members)
        monkeypatch.setattr(sched, "_sleep_or_join", self._sleep)
        monkeypatch.setattr(joiner, "hangup", self._hangup)
        monkeypatch.setattr(sched, "hangup", self._hangup)

    def _hangup_button(self, *a, **k):
        self.checks += 1
        return object() if self.in_call(self.i) else None

    def _members(self):
        return self.counts[min(self.i, len(self.counts) - 1)]

    def _sleep(self, seconds):
        self.i += 1
        self.now += timedelta(seconds=seconds)
        if self.on_sleep:
            self.on_sleep(self)
        if self.i > 2000:
            raise AssertionError("never left the class")

    def _hangup(self):
        if not self.hangup_works or rt.current_meeting is None:
            return False
        rt.left_by_bot = True
        self.left_at = self.i
        rt.current_meeting = None
        return True


def setup_function():
    status.reset()          # an earlier test may have left "stop" requested
    rt.config = {"leave_if_last": True, "min_members": 3,
                 "check_interval": INTERVAL}
    rt.current_meeting = _Meeting()
    rt.hangup_thread = None
    rt.handled = set()
    rt.schedule = []
    rt.join_request = None
    rt.leave_request = False
    rt.left_by_bot = False
    rt.rejoins = {}
    rt.peaks = {}


def _entry(title="Lập trình Python", start=START, hours=2):
    return {"title": title, "start": start, "end": start + timedelta(hours=hours)}


# ── the leave rules ──────────────────────────────────────────────────────────

def test_joining_early_into_an_empty_class_does_not_leave_it(monkeypatch):
    # Alone for a minute, then the teacher, then the students arrive.
    counts = [1] * 8 + [2] * 8 + [25] * 30
    cls = _Class(monkeypatch, counts,
                 in_call=lambda i: i < len(counts))   # the class ends normally

    sched._stay_until_meeting_ends(_entry())

    assert cls.left_at is None


def test_a_class_that_has_emptied_out_is_left(monkeypatch):
    counts = [25] * 10 + [2] * 10
    cls = _Class(monkeypatch, counts)

    sched._stay_until_meeting_ends(_entry())

    # Left once the drop had held for the confirmation window, not before.
    assert cls.left_at is not None
    assert 10 < cls.left_at <= 10 + 3


def test_one_bad_reading_does_not_drop_a_healthy_class(monkeypatch):
    counts = [30] * 5 + [1] + [30] * 20
    cls = _Class(monkeypatch, counts, in_call=lambda i: i < len(counts))

    sched._stay_until_meeting_ends(_entry())

    assert cls.left_at is None


def test_unreadable_counts_neither_confirm_nor_trigger_a_leave(monkeypatch):
    counts = [25] * 5 + [None, 2, None, None, 25] + [25] * 10
    cls = _Class(monkeypatch, counts, in_call=lambda i: i < len(counts))

    sched._stay_until_meeting_ends(_entry())

    assert cls.left_at is None


def test_unreadable_counts_do_not_reset_a_pending_leave(monkeypatch):
    counts = [25] * 5 + [2, None, 2, None, 2] + [25] * 10
    cls = _Class(monkeypatch, counts)

    sched._stay_until_meeting_ends(_entry())

    assert cls.left_at == 9          # the third low reading, gaps and all


def test_a_failed_hang_up_is_not_reported_as_leaving():
    rt.config = {"min_members": 3}
    joiner_hangup = joiner.hangup
    try:
        joiner.hangup = lambda: False
        assert joiner.handle_leave_threshold(1, 20) is False
    finally:
        joiner.hangup = joiner_hangup
    # Still marked as in the call, so the loop keeps watching it instead of
    # heading off with a stale rt.current_meeting that blocks the next join.
    assert rt.current_meeting is not None


def test_when_the_hang_up_fails_the_loop_keeps_watching_the_call(monkeypatch):
    counts = [25] * 5 + [2] * 20
    cls = _Class(monkeypatch, counts, hangup_works=False,
                 in_call=lambda i: i < 15)            # call ends on its own later

    outcome = sched._stay_until_meeting_ends(_entry())

    assert rt.current_meeting is None                  # cleared by the end check
    assert cls.i >= 15                                 # did not bail out early
    # We had decided to leave: the call going away is that, not a drop to
    # re-join — going back in would undo the leave rule.
    assert outcome is None


def test_leave_reason_needs_the_class_to_have_gathered_first():
    rt.config = {"min_members": 3}

    assert joiner.leave_reason(1, 2) is None     # never reached 3 people
    assert joiner.leave_reason(2, 20) is not None


# ── moving on to the next class ─────────────────────────────────────────────

def test_a_call_that_never_ends_is_left_for_the_next_class(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    now = _entry()
    nxt = _entry("Cấu trúc dữ liệu", start=START + timedelta(hours=2))
    rt.schedule = [now, nxt]
    rt.handled = {sched._key(now)}
    cls = _Class(monkeypatch, [30], now=START)

    sched._stay_until_meeting_ends(now, join_before=2)

    assert cls.left_at is not None
    assert rt.current_meeting is None
    left = cls.now
    assert nxt["start"] - timedelta(minutes=2) <= left \
        <= nxt["start"] - timedelta(minutes=2) + timedelta(seconds=INTERVAL)


def test_an_overlapping_event_does_not_cut_the_current_class_short(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    now = _entry(hours=2)                                         # 07:00–09:00
    overlap = _entry("Họp nhóm", start=START + timedelta(hours=1))  # 08:00
    rt.schedule = [now, overlap]
    rt.handled = {sched._key(now)}

    assert sched._switch_at(now, 2) == now["end"] - timedelta(minutes=2)


def test_with_no_later_class_it_stays_until_the_call_ends(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    rt.schedule = [_entry()]
    cls = _Class(monkeypatch, [30], in_call=lambda i: i < 40, now=START)

    sched._stay_until_meeting_ends(_entry(), join_before=2)

    assert cls.left_at is None
    assert cls.i == 40


def test_a_class_already_attended_is_not_a_reason_to_leave(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    later = _entry("Đã học rồi", start=START + timedelta(minutes=30))
    rt.schedule = [_entry(), later]
    rt.handled = {sched._key(later)}

    assert sched._switch_at(_entry(), 2) is None


def test_the_switch_goes_through_even_if_the_hang_up_button_is_gone(monkeypatch):
    # Joining the next class navigates away from this one anyway; what must
    # not survive is a stale rt.current_meeting, which would stop the join
    # loop from even trying.
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    now = _entry()
    rt.schedule = [now, _entry("Buổi sau", start=START + timedelta(hours=2))]
    rt.handled = {sched._key(now)}
    _Class(monkeypatch, [30], hangup_works=False, now=START)

    sched._stay_until_meeting_ends(now, join_before=2)

    assert rt.current_meeting is None


# ── the call going away on its own ───────────────────────────────────────────

def test_a_call_that_drops_mid_class_is_reported_as_dropped(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    _Class(monkeypatch, [30], in_call=lambda i: i < 30, now=START)

    assert sched._stay_until_meeting_ends(_entry()) == sched.DROPPED
    assert rt.current_meeting is None


def test_the_toolbar_missing_for_one_check_is_not_the_end(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    cls = _Class(monkeypatch, [30], in_call=lambda i: i < 30, now=START)
    flicker = cls._hangup_button

    def once_missing(*a, **k):
        found = flicker(*a, **k)
        return None if cls.checks == 4 else found    # a re-render, say

    monkeypatch.setattr(sched, "wait_until_found", once_missing)

    sched._stay_until_meeting_ends(_entry())

    assert cls.i == 30                                 # watched to the real end


def test_the_auto_leave_timer_hanging_up_is_not_a_drop(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}

    def timer_fires(cls):
        if cls.i == 6:                  # hangup() from the Timer thread
            rt.left_by_bot = True
            cls.in_call = lambda i: False

    _Class(monkeypatch, [30], now=START, on_sleep=timer_fires)

    assert sched._stay_until_meeting_ends(_entry()) is None


def test_leaving_on_a_rule_is_not_a_drop(monkeypatch):
    _Class(monkeypatch, [25] * 5 + [2] * 10)

    assert sched._stay_until_meeting_ends(_entry()) is None


def _dropped_entry(minutes_in=30):
    now = START + timedelta(minutes=minutes_in)
    return _entry(), now


def test_a_dropped_class_is_put_back_up_for_joining():
    entry, now = _dropped_entry()
    rt.handled = {sched._key(entry)}

    assert sched._rearm_after_drop(entry, sched.DROPPED, now) is True
    assert sched._key(entry) not in rt.handled
    # ... and, still running, it is what the next pass goes to.
    assert sched._pick_order([entry], now) == [entry]


def test_a_class_we_left_on_purpose_is_not_rejoined():
    entry, now = _dropped_entry()
    rt.handled = {sched._key(entry)}

    assert sched._rearm_after_drop(entry, None, now) is False
    assert sched._key(entry) in rt.handled


def test_no_rejoin_when_the_class_is_about_to_end():
    entry, _ = _dropped_entry()
    near_end = entry["end"] - timedelta(minutes=5)

    assert sched._may_rejoin(entry, near_end) is False


def test_no_rejoin_without_a_known_end_time():
    # Classes scraped off the page have no end time: nothing tells a dropped
    # call from a finished class.
    entry = {"title": "Buổi từ kênh", "start": START}

    assert sched._may_rejoin(entry, START + timedelta(minutes=30)) is False


def test_rejoins_are_capped_per_class():
    entry, now = _dropped_entry()

    assert sched._rearm_after_drop(entry, sched.DROPPED, now) is True
    assert sched._rearm_after_drop(entry, sched.DROPPED, now) is True
    assert sched._rearm_after_drop(entry, sched.DROPPED, now) is False


def test_rejoining_can_be_turned_off():
    rt.config = {"max_rejoins": 0}
    entry, now = _dropped_entry()

    assert sched._may_rejoin(entry, now) is False


def test_back_in_after_a_drop_an_emptied_room_is_left(monkeypatch):
    # The teacher ended class, the bot took it for a drop and went back in:
    # the peak of the class it was in carries over, so being alone now reads
    # as the class having emptied rather than one yet to gather.
    entry = _entry()
    rt.rejoins = {sched._key(entry): 1}
    rt.peaks = {sched._key(entry): 25}
    cls = _Class(monkeypatch, [1] * 20, now=START + timedelta(minutes=40))

    assert sched._stay_until_meeting_ends(entry) is None
    assert cls.left_at is not None and cls.left_at <= 3


def test_back_in_after_a_drop_the_bot_leaves_at_the_scheduled_end(monkeypatch):
    # Without a readable roster nothing else would ever end a re-joined,
    # restarted meeting, so the class's own end time does.
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    entry = _entry(hours=1)
    rt.schedule = [entry]
    rt.rejoins = {sched._key(entry): 1}
    cls = _Class(monkeypatch, [1], now=START + timedelta(minutes=40))

    sched._stay_until_meeting_ends(entry)

    assert cls.left_at is not None
    assert entry["end"] <= cls.now <= entry["end"] + timedelta(seconds=INTERVAL)


def test_a_first_visit_does_not_leave_at_the_scheduled_end(monkeypatch):
    # Classes run over; only a re-joined one is cut at its end time.
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    entry = _entry(hours=1)
    rt.schedule = [entry]
    cls = _Class(monkeypatch, [1], in_call=lambda i: i < 500,
                 now=START + timedelta(minutes=40))

    sched._stay_until_meeting_ends(entry)

    assert cls.left_at is None


# ── requests from the dashboard ─────────────────────────────────────────────

def test_leave_button_hangs_up_and_is_not_a_drop(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}

    def click(cls):
        if cls.i == 3:
            rt.leave_request = True

    cls = _Class(monkeypatch, [30], now=START, on_sleep=click)

    assert sched._stay_until_meeting_ends(_entry()) is None
    assert cls.left_at == 3
    assert rt.leave_request is False


def test_a_leave_click_meant_for_the_previous_class_is_ignored(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    rt.leave_request = True
    cls = _Class(monkeypatch, [30], in_call=lambda i: i < 10, now=START)

    sched._stay_until_meeting_ends(_entry())

    assert cls.left_at is None


def test_picking_another_class_on_the_dashboard_leaves_this_one(monkeypatch):
    rt.config = {"leave_if_last": False, "check_interval": INTERVAL}
    other = _entry("Cấu trúc dữ liệu", start=START + timedelta(hours=3))

    def click(cls):
        if cls.i == 4:
            rt.join_request = other

    cls = _Class(monkeypatch, [30], now=START, on_sleep=click)

    assert sched._stay_until_meeting_ends(_entry()) is None
    assert cls.left_at == 4
    assert rt.join_request is other          # left for the main loop to take
