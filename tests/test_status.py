import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import status


def setup_function(_):
    status.reset()


def test_report_and_snapshot():
    status.report("countdown", title="Toán", join_at=123.0, detail="Còn 5 phút")
    snap = status.snapshot()
    assert snap["state"] == "countdown"
    assert snap["title"] == "Toán"
    assert snap["join_at"] == 123.0
    assert snap["detail"] == "Còn 5 phút"


def test_partial_report_keeps_other_fields():
    status.report("countdown", title="Toán", join_at=123.0)
    status.report(detail="chỉ đổi detail")
    snap = status.snapshot()
    assert snap["state"] == "countdown"
    assert snap["title"] == "Toán"
    assert snap["detail"] == "chỉ đổi detail"


def test_log_appends_and_caps(capsys):
    for i in range(250):
        status.log(f"msg {i}")
    snap = status.snapshot()
    assert len(snap["logs"]) == 200
    assert snap["logs"][-1]["msg"] == "msg 249"
    assert "msg 249" in capsys.readouterr().out


def test_check_stop_raises():
    status.stop_requested.set()
    try:
        status.check_stop()
        assert False, "should have raised"
    except status.BotStopped:
        pass


def test_sleep_checked_aborts_quickly():
    status.stop_requested.set()
    try:
        status.sleep_checked(30)
        assert False, "should have raised"
    except status.BotStopped:
        pass
