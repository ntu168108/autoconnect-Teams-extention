"""Channel meeting-banner time parsing, in both UI languages.

An English-locale account used to fall through every regex here, so channel
discovery reported no classes at all — forever, and silently.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import scanner


def test_vietnamese_banner():
    aria = ("Cuộc họp đã lên lịch. BUỔI 2 - CNXHKH. "
            "Thứ Hai, 9 tháng 2, 2026 12:30. Nhấn enter để tham gia")

    assert scanner._parse_banner_time(aria) == datetime(2026, 2, 9, 12, 30)


def test_english_banner():
    aria = ("Scheduled meeting. Math class. "
            "Monday, February 9, 2026 12:30 PM. Press enter to join")

    assert scanner._parse_banner_time(aria) == datetime(2026, 2, 9, 12, 30)


def test_english_midnight_and_noon():
    midnight = "Scheduled meeting. X. Monday, February 9, 2026 12:15 AM."
    noon = "Scheduled meeting. X. Monday, February 9, 2026 12:15 PM."

    assert scanner._parse_banner_time(midnight) == datetime(2026, 2, 9, 0, 15)
    assert scanner._parse_banner_time(noon) == datetime(2026, 2, 9, 12, 15)


def test_english_morning_stays_in_the_morning():
    aria = "Scheduled meeting. X. Monday, February 9, 2026 7:05 AM."

    assert scanner._parse_banner_time(aria) == datetime(2026, 2, 9, 7, 5)


def test_a_date_inside_the_title_is_not_mistaken_for_the_schedule():
    aria = "Cuộc họp đã lên lịch. Ngày 03.02.2026 Lúc 07h15. Nhấn enter"

    assert scanner._parse_banner_time(aria) is None


def test_nonsense_and_empty_input():
    assert scanner._parse_banner_time("") is None
    assert scanner._parse_banner_time(None) is None
    assert scanner._parse_banner_time("Scheduled meeting. No date here.") is None


def test_impossible_date_is_rejected_rather_than_raising():
    aria = "Scheduled meeting. X. Monday, February 31, 2026 10:00 AM."

    assert scanner._parse_banner_time(aria) is None
