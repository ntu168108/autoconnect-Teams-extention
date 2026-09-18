"""The 'Vào lớp ngay' button on the dashboard hands the bot an index into the
last scan; these cover how the schedule loop consumes it."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import runtime as rt
import schedule as sched


def setup_function():
    rt.schedule = []
    rt.join_request = None
    rt.joining = False
    rt.handled = set()


def test_returns_the_clicked_class_and_clears_the_request():
    rt.join_request = {"start": datetime(2026, 9, 16, 13, 0), "title": "Buổi 2"}

    assert sched._take_join_request()["title"] == "Buổi 2"
    # Cleared, so the next loop iteration does not re-join it.
    assert rt.join_request is None
    assert sched._take_join_request() is None


def test_no_request_pending_returns_none():
    assert sched._take_join_request() is None


def test_request_survives_a_rescan_that_reorders_the_schedule():
    # The dashboard resolves the click to the class itself, so re-scanning
    # (which rebuilds rt.schedule) cannot make it point at a different class.
    clicked = {"start": datetime(2026, 9, 16, 13, 0), "title": "Buổi 2"}
    rt.schedule = [clicked, {"start": datetime(2026, 9, 9, 13, 0), "title": "Buổi 1"}]
    rt.join_request = clicked

    rt.schedule = [{"start": datetime(2026, 9, 30, 13, 0), "title": "Buổi 9"}]

    assert sched._take_join_request()["title"] == "Buổi 2"


def test_click_on_the_class_being_joined_is_discarded_not_replayed_later():
    # rt.current_meeting stays None for the first ~30-40s of a join, so a click
    # in that window is accepted. If it were kept, it would be consumed at the
    # start of the NEXT cycle and send the bot back to the class that just
    # ended — burning the join window of the class it should be attending.
    clicked = {"start": datetime(2026, 9, 9, 13, 0), "title": "Buổi 1"}
    rt.join_request = clicked
    rt.handled = {sched._key(clicked)}

    assert sched._take_join_request() is None
    assert rt.join_request is None


def test_a_class_not_yet_attended_is_still_honoured():
    clicked = {"start": datetime(2026, 9, 16, 13, 0), "title": "Buổi 2"}
    rt.join_request = clicked
    rt.handled = {sched._key({"start": datetime(2026, 9, 9, 13, 0), "title": "Buổi 1"})}

    assert sched._take_join_request()["title"] == "Buổi 2"


def _meeting(start):
    return {"title": "Buổi kế tiếp", "start": start}


def test_countdown_reports_not_reached_while_a_click_is_pending():
    # Otherwise a click that cannot be honoured would make the caller treat the
    # countdown as finished and join the *next* class ahead of its start time.
    rt.join_request = {"start": datetime(2026, 9, 16, 13, 0), "title": "Buổi 2"}
    start = datetime.now() + timedelta(hours=2)

    assert sched._countdown_until(_meeting(start), start, max_seconds=5) is False


def test_countdown_reports_reached_once_the_join_time_passes():
    start = datetime.now() - timedelta(seconds=1)

    assert sched._countdown_until(_meeting(start), start, max_seconds=5) is True
