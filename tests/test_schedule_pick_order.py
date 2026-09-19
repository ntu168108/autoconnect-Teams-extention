"""Which class the bot goes to next.

Sorting purely by start time picks the OLDEST class still inside the lookback
window — typically one that has already ended — instead of the class actually
running right now.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import runtime as rt
import schedule as sched

NOW = datetime(2026, 9, 18, 15, 0)


def setup_function():
    rt.handled = set()
    rt.config = {}


def _cls(title, start_h, hours=3.5):
    start = NOW + timedelta(hours=start_h)
    return {"title": title, "start": start, "end": start + timedelta(hours=hours)}


def test_class_running_right_now_wins_over_an_earlier_one_that_ended():
    ended = _cls("Buổi cũ đã tan", -4)        # 11:00–14:30, over
    running = _cls("Buổi đang học", -1)       # 14:00–17:30, in progress
    later = _cls("Buổi ngày mai", 24)

    order = sched._pick_order([ended, running, later], NOW)

    assert [m["title"] for m in order] == ["Buổi đang học", "Buổi ngày mai"]


def test_finished_classes_are_dropped_even_inside_the_lookback_window():
    # Started 2h ago but only ran 1h — sorting by start alone would keep it.
    finished = _cls("Buổi ngắn đã xong", -2, hours=1)

    assert sched._pick_order([finished], NOW) == []


def test_the_most_recently_started_class_comes_first():
    older = _cls("Bắt đầu 2 tiếng trước", -2)
    newer = _cls("Bắt đầu 30 phút trước", -0.5)

    order = sched._pick_order([older, newer], NOW)

    assert order[0]["title"] == "Bắt đầu 30 phút trước"


def test_upcoming_classes_are_soonest_first():
    order = sched._pick_order([_cls("Xa", 5), _cls("Gần", 1)], NOW)

    assert [m["title"] for m in order] == ["Gần", "Xa"]


def test_classes_already_attended_are_not_offered_again():
    done = _cls("Đã học", -1)
    rt.handled = {sched._key(done)}

    assert sched._pick_order([done], NOW) == []


def test_without_an_end_time_it_falls_back_to_the_staleness_window():
    # The scraped calendar path carries no end time.
    recent = {"title": "Vừa bắt đầu", "start": NOW - timedelta(hours=1)}
    stale = {"title": "Quá cũ", "start": NOW - timedelta(hours=5)}

    order = sched._pick_order([recent, stale], NOW)

    assert [m["title"] for m in order] == ["Vừa bắt đầu"]


def test_a_class_with_no_subject_still_wins_over_one_days_away():
    """Reported from a live run: a class was running right then, yet the bot
    counted down ~94 hours to one four days later. The calendar API had
    dropped it for having no subject, so the picker never saw it."""
    import json

    import teams_api

    def _raw(subject, start, minutes):
        end = start + timedelta(minutes=minutes)
        return {
            "Start": start.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "End": end.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
            "Subject": subject,
            "IsCancelled": False,
            "SkypeTeamsProperties": json.dumps(
                {"cid": "19:x@thread.tacv2", "rid": "1"}),
        }

    events = teams_api._parse_items([
        _raw("BUỔI 2 - CNXHKH", NOW - timedelta(hours=21), 120),   # finished
        _raw(None, NOW - timedelta(minutes=9), 30),                # running now
        _raw("Buổi 3", NOW + timedelta(days=4), 210),
    ])

    assert len(events) == 3        # the untitled one is kept
    assert sched._pick_order(events, NOW)[0]["title"] == "(Không có chủ đề)"


def test_staleness_window_is_configurable():
    stale = {"title": "5 tiếng trước", "start": NOW - timedelta(hours=5)}

    assert sched._pick_order([stale], NOW) == []
    rt.config = {"stale_after_hours": 6}
    assert len(sched._pick_order([stale], NOW)) == 1
