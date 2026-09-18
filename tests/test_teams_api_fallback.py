"""fetch_calendar_events must answer None (→ caller scrapes the page) whenever
it cannot trust the API, and only ever answer [] for a genuinely empty
calendar. Answering [] on a broken response would read as "no classes today"
and the bot would quietly never join anything."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import runtime as rt
import teams_api


class _FakeBrowser:
    def __init__(self, result):
        self._result = result

    def set_script_timeout(self, _seconds):
        pass

    def execute_async_script(self, _script, *_args):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _run(result):
    rt.browser = _FakeBrowser(result)
    return teams_api.fetch_calendar_events()


def _response(items):
    return {"ok": True, "data": {"Body": {"Items": items}}}


_GOOD_ITEM = {
    "Start": "2026-09-09T13:00:00+07:00",
    "Subject": "Buổi 1",
    "IsCancelled": False,
}


def test_empty_calendar_is_a_real_answer_not_a_failure():
    assert _run(_response([])) == []


def test_good_response_is_parsed():
    events = _run(_response([_GOOD_ITEM]))
    assert [e["title"] for e in events] == ["Buổi 1"]


def test_events_that_all_fail_to_parse_fall_back_instead_of_reporting_none_found():
    unreadable = [{"Start": "không phải ngày giờ", "Subject": "Buổi 1"}]
    assert _run(_response(unreadable)) is None


def test_unexpected_response_shape_falls_back():
    assert _run({"ok": True, "data": {"Body": {}}}) is None
    assert _run({"ok": True, "data": {}}) is None


def test_fetch_error_reported_by_the_page_falls_back():
    assert _run({"ok": False, "error": "HTTP 401"}) is None


def test_driver_blowing_up_falls_back():
    assert _run(RuntimeError("script timeout")) is None
