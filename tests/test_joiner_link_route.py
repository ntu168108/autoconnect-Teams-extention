"""Joining through the meeting's own Teams link, with the calendar UI as the
fallback. The link is exact and is not limited to the calendar week on screen,
but it is an undocumented deep-link format — so failing over must be reliable.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import joiner
import runtime as rt
from models import Meeting


class _FakeBrowser:
    def __init__(self, fail_on_get=False):
        self.visited = []
        self.fail_on_get = fail_on_get

    def get(self, url):
        self.visited.append(url)
        if self.fail_on_get:
            raise RuntimeError("navigation blew up")


def _meeting(**over):
    kwargs = dict(m_id="calendar:x", title="Buổi 1",
                  calendar_meeting=True,
                  thread_id="19:aaaaaaaabbbbccccddddeeeeffff0000@thread.tacv2",
                  reply_id="1700000000000")
    kwargs.update(over)
    return Meeting(**kwargs)


def setup_function():
    rt.config = {}
    rt.browser = _FakeBrowser()


def _finder(monkeypatch, **by_selector):
    """Stub wait_until_found: map each selector to the sequence of answers it
    should give (an element, or None for 'not there')."""
    seqs = {sel: list(vals) for sel, vals in by_selector.items()}
    clicks = []
    monkeypatch.setattr(joiner.rt.browser, "execute_script",
                        lambda script, *a: clicks.append(a), raising=False)

    def fake(selector, _timeout, **_kw):
        vals = seqs.get(selector)
        if not vals:
            return None
        return vals.pop(0)

    monkeypatch.setattr(joiner, "wait_until_found", fake)
    return clicks


WEB_LINK = ("https://teams.microsoft.com/_#/l/meetup-join/"
            "19%3Aaaaaaaaabbbbccccddddeeeeffff0000%40thread.tacv2/1700000000000")


def test_the_link_forces_the_web_client(monkeypatch):
    # Without the "_#" segment Teams serves its launcher page, which hands off
    # to the desktop app and makes Chrome raise a native dialog over the
    # window that selenium cannot dismiss.
    _finder(monkeypatch, **{joiner.S.SEL_PREJOIN_SCREEN: [object()]})

    assert joiner._open_meeting_by_link(_meeting()) is True
    assert rt.browser.visited == [WEB_LINK]


def test_a_meeting_thread_uses_reply_id_zero(monkeypatch):
    _finder(monkeypatch, **{joiner.S.SEL_PREJOIN_SCREEN: [object()]})

    joiner._open_meeting_by_link(
        _meeting(thread_id="19:meeting_abc@thread.v2", reply_id=None))

    assert rt.browser.visited[0].endswith("/0")


def test_the_launcher_page_is_clicked_through_to_the_browser(monkeypatch):
    # The link lands on "open the app, or continue in this browser?" — the bot
    # must press the browser option, then carry on to the pre-join screen.
    button = object()
    clicks = _finder(monkeypatch, **{
        joiner.S.SEL_PREJOIN_SCREEN: [None, object()],
        joiner.S.SEL_LAUNCHER_JOIN_WEB: [button],
    })

    assert joiner._open_meeting_by_link(_meeting()) is True
    assert clicks == [(button,)]          # and never the "open the app" one


def test_without_a_thread_id_it_declines_so_the_caller_falls_back():
    assert joiner._open_meeting_by_link(_meeting(thread_id=None)) is False
    assert rt.browser.visited == []          # no wasted page load


def _fast_clock(monkeypatch, step=30):
    clock = {"t": 0}

    def _now():
        clock["t"] += step
        return clock["t"]

    monkeypatch.setattr(joiner.time, "time", _now)


def test_landing_in_the_teams_app_hands_over_without_reloading(monkeypatch):
    # Seen live: the link opened Teams but showed the teams grid, not the
    # class. The app we need is already loaded, so reloading it would only
    # cost the fallback another 10-30s for nothing.
    _finder(monkeypatch, **{joiner.S.SEL_PAGE_READY: [object()] * 100})
    _fast_clock(monkeypatch, step=1)          # let the grace period elapse

    assert joiner._open_meeting_by_link(_meeting()) is False
    assert rt.browser.visited == [WEB_LINK]           # only the link itself


def test_the_class_is_given_a_grace_period_after_teams_comes_up(monkeypatch):
    # Teams reports ready before the pre-join screen renders, so giving up the
    # moment the app appears would abandon a join that was about to succeed.
    _finder(monkeypatch, **{
        joiner.S.SEL_PREJOIN_SCREEN: [None, None, object()],
        joiner.S.SEL_PAGE_READY: [object(), object()],
    })
    _fast_clock(monkeypatch, step=1)

    assert joiner._open_meeting_by_link(_meeting()) is True


def test_a_dead_end_returns_to_teams_so_the_calendar_route_still_works(monkeypatch):
    # Navigating to the link takes the whole window away from the Teams app.
    # Without coming back, the calendar fallback just reports "iframe not
    # found" and the class is missed entirely.
    _finder(monkeypatch)                      # nothing is ever found
    _fast_clock(monkeypatch)                  # close the window without delay

    assert joiner._open_meeting_by_link(_meeting()) is False
    assert rt.browser.visited[-1] == "https://teams.microsoft.com"


def test_navigation_error_also_returns_to_teams(monkeypatch):
    rt.browser = _FakeBrowser(fail_on_get=True)
    _finder(monkeypatch)

    assert joiner._open_meeting_by_link(_meeting()) is False
    # Both the link and the recovery attempt were tried.
    assert rt.browser.visited[-1] == "https://teams.microsoft.com"


def test_a_dead_browser_still_propagates(monkeypatch):
    # A closed Chrome must end the run, not silently fall through to a route
    # that cannot work either.
    class _Dead(_FakeBrowser):
        def get(self, url):
            raise RuntimeError("invalid session id")

    rt.browser = _Dead()
    monkeypatch.setattr(joiner, "browser_dead", lambda e: True)

    try:
        joiner._open_meeting_by_link(_meeting())
    except RuntimeError:
        return
    raise AssertionError("phai nem lai loi khi Chrome da dong")
