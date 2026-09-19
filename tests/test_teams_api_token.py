"""Getting hold of the Bearer token OWA uses.

A live session showed the token is not in web storage at all, so the probe
watches OWA's own requests for it. The waiting rules matter: we accept a
one-off delay the first time the probe goes in, but must not re-pay it on
every later scan when it is clear nothing is coming.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import runtime as rt
import teams_api


class _FakeBrowser:
    """Answers the probe's install/read scripts; `tokens` is read in order."""

    def __init__(self, install_result="installed", tokens=(), explode=False):
        self.install_result = install_result
        self.tokens = list(tokens)
        self.explode = explode
        self.reads = 0

    def execute_script(self, script, *args):
        if self.explode:
            raise RuntimeError("javascript blew up")
        if "__tajProbe = {token: null}" in script:
            return self.install_result
        self.reads += 1
        return self.tokens.pop(0) if self.tokens else None


def setup_function():
    rt.config = {}


def test_token_already_waiting_is_returned_without_delay():
    rt.browser = _FakeBrowser(tokens=["TOKEN_ABC"])

    assert teams_api._capture_token(10) == "TOKEN_ABC"
    assert rt.browser.reads == 1


def test_it_waits_for_owa_to_make_a_call_on_a_fresh_probe(monkeypatch):
    monkeypatch.setattr(teams_api.time, "sleep", lambda s: None)
    # Nothing on the first two looks, then OWA fires a request.
    rt.browser = _FakeBrowser(tokens=[None, None, "TOKEN_LATE"])

    assert teams_api._capture_token(10) == "TOKEN_LATE"


def test_an_already_installed_probe_with_nothing_does_not_wait_again(monkeypatch):
    slept = []
    monkeypatch.setattr(teams_api.time, "sleep", lambda s: slept.append(s))
    rt.browser = _FakeBrowser(install_result="already", tokens=[None])

    assert teams_api._capture_token(10) is None
    assert slept == []          # no repeated stall on every scan


def test_giving_up_when_the_wait_runs_out(monkeypatch):
    monkeypatch.setattr(teams_api.time, "sleep", lambda s: None)
    rt.browser = _FakeBrowser(tokens=[None] * 50)

    assert teams_api._capture_token(0) is None


def test_a_broken_page_reports_no_token_rather_than_raising():
    rt.browser = _FakeBrowser(explode=True)

    assert teams_api._capture_token(10) is None
