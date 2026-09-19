"""Parsing of Outlook's GetCalendarView response.

The fixtures mirror the shape of a real response (verified against a live
capture) but use synthetic subjects and thread ids.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import teams_api


def _item(**over):
    item = {
        "__type": "CalendarItem:#Exchange",
        "Start": "2026-09-09T13:00:00+07:00",
        "End": "2026-09-09T16:30:00+07:00",
        "Subject": "Buổi 1_13h10-16h30_Môn Tư tưởng HCM",
        "IsMeeting": True,
        "IsCancelled": False,
        "SkypeTeamsProperties": json.dumps({
            "cid": "19:abc123@thread.tacv2",
            "rid": "1700000000000",
            "private": False,
            "type": 0,
        }),
    }
    item.update(over)
    return item


def test_parses_subject_start_and_thread_id():
    (ev,) = teams_api._parse_items([_item()])
    assert ev["title"] == "Buổi 1_13h10-16h30_Môn Tư tưởng HCM"
    assert ev["cid"] == "19:abc123@thread.tacv2"
    assert ev["source"] == "calendar"
    assert isinstance(ev["start"], datetime)


def test_start_is_converted_to_naive_local_time():
    # The rest of the bot compares against datetime.now(), which is naive.
    (ev,) = teams_api._parse_items([_item()])
    assert ev["start"].tzinfo is None
    # Same instant, expressed in whatever timezone the machine runs in.
    expected = datetime.fromisoformat(
        "2026-09-09T13:00:00+07:00").astimezone().replace(tzinfo=None)
    assert ev["start"] == expected


def test_cancelled_classes_are_skipped():
    assert teams_api._parse_items([_item(IsCancelled=True)]) == []


def test_event_without_teams_properties_still_parses():
    (ev,) = teams_api._parse_items([_item(SkypeTeamsProperties=None)])
    assert ev["cid"] is None
    assert ev["title"]


def test_malformed_teams_properties_does_not_break_the_scan():
    (ev,) = teams_api._parse_items([_item(SkypeTeamsProperties="{not json")])
    assert ev["cid"] is None


def test_items_missing_a_start_are_skipped():
    assert teams_api._parse_items([
        _item(Start=None),
        _item(Start="rác không phải ngày giờ"),
    ]) == []


def test_an_event_with_no_subject_is_still_a_class_to_join():
    # Outlook shows these as "(Không có chủ đề)". Dropping them meant the bot
    # skipped a class that was happening right then and counted down to one
    # four days away instead.
    for subject in (None, "", "   "):
        (ev,) = teams_api._parse_items([_item(Subject=subject)])
        assert ev["title"] == "(Không có chủ đề)"
        assert ev["cid"]          # still joinable via its own link


def test_mixed_batch_keeps_only_the_usable_events():
    events = teams_api._parse_items([
        _item(Subject="Buổi 1"),
        _item(Subject="Buổi 2 đã hủy", IsCancelled=True),
        _item(Subject="Buổi 3", Start="2026-09-16T13:00:00+07:00"),
    ])
    assert [e["title"] for e in events] == ["Buổi 1", "Buổi 3"]


def test_payload_requests_teams_properties_and_the_default_calendar():
    # Without IncludeSkypeTeamsProperties the response carries no thread ids,
    # and the distinguished folder id avoids a second lookup call.
    body = teams_api._payload(datetime(2026, 9, 1), datetime(2026, 10, 1),
                              "SE Asia Standard Time")["Body"]
    assert body["IncludeSkypeTeamsProperties"] is True
    assert body["CalendarId"]["BaseFolderId"]["Id"] == "calendar"
    assert body["RangeStart"] == "2026-09-01T00:00:00.000"
    assert body["RangeEnd"] == "2026-10-01T00:00:00.000"
