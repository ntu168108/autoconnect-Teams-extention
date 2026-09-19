"""Chrome preferences the bot depends on.

Each of these exists to stop a browser-level prompt appearing over the page:
selenium drives page content, so anything Chrome itself draws on top blocks
the run until a human clicks it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import browser


def test_camera_and_mic_prompts_stay_suppressed():
    # Otherwise the pre-join screen sits behind a permission prompt.
    prefs = browser.CHROME_PREFS

    assert prefs["profile.default_content_setting_values.media_stream_mic"] == 1
    assert prefs["profile.default_content_setting_values.media_stream_camera"] == 1


def test_password_manager_stays_off():
    # A "save password?" bubble can cover the login form mid-run.
    assert browser.CHROME_PREFS["credentials_enable_service"] is False
    assert browser.CHROME_PREFS["profile"]["password_manager_enabled"] is False
