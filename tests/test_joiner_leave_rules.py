"""Leave-the-class rules and the auto-leave timer's lifecycle.

Both matter across a long unattended run: a bad reading must never drop the
bot out of a class that is going fine, and a timer armed for one class must
never fire during the next one.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import joiner
import runtime as rt


class _FakeMeeting:
    title = "Buổi 1"


def setup_function():
    rt.config = {}
    rt.current_meeting = _FakeMeeting()
    rt.hangup_thread = None


def test_unreadable_roster_never_triggers_a_leave():
    # get_meeting_members can answer 0 when the People panel fails to parse.
    # We are in the call, so 0 is impossible — treat it as "unknown".
    rt.config = {"leave_threshold_percentage": 50, "min_members": 3,
                 "leave_threshold_number": 2}

    assert joiner.handle_leave_threshold(0, 20) is False
    assert rt.current_meeting is not None


def test_percentage_rule_does_not_divide_by_zero_before_a_peak_is_known():
    # rt.total_members starts at 0, so the first check can arrive with total=0.
    rt.config = {"leave_threshold_percentage": 50}

    assert joiner.handle_leave_threshold(0, 0) is False


def test_healthy_class_is_not_left():
    rt.config = {"min_members": 3, "leave_threshold_percentage": 50}

    assert joiner.handle_leave_threshold(18, 20) is False


class _FakeTimer:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_cancel_auto_leave_clears_the_pending_timer():
    timer = _FakeTimer()
    rt.hangup_thread = timer

    joiner._cancel_auto_leave()

    assert timer.cancelled is True
    assert rt.hangup_thread is None


def test_cancelling_twice_is_harmless():
    joiner._cancel_auto_leave()
    joiner._cancel_auto_leave()

    assert rt.hangup_thread is None
