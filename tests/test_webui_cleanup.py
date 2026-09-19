"""Shutdown cleanup. This runs from main.py's `finally`, so it must never
raise — whatever state the run died in."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import webui


def teardown_function():
    webui._server = None


def test_safe_when_nothing_was_started():
    webui._server = None

    webui.close_app_window()          # must not raise


def test_calling_it_twice_is_safe():
    webui._server = None

    webui.close_app_window()
    webui.close_app_window()


def test_a_server_that_fails_to_shut_down_does_not_break_the_exit_path():
    class _StubbornServer:
        def shutdown(self):
            raise RuntimeError("shutdown failed")

        def server_close(self):
            raise RuntimeError("close failed")

    webui._server = _StubbornServer()

    webui.close_app_window()

    assert webui._server is None      # still cleared


def test_the_server_is_shut_down_and_cleared():
    calls = []

    class _Server:
        def shutdown(self):
            calls.append("shutdown")

        def server_close(self):
            calls.append("close")

    webui._server = _Server()

    webui.close_app_window()

    assert calls == ["shutdown", "close"]
    assert webui._server is None
