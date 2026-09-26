"""The in-page scripts that read the class headcount, run under node against
a minimal fake DOM. Skipped when node is not installed."""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import joiner

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

_HARNESS = r"""
var dom = %(dom)s;
function node(spec) {
  return {
    getAttribute: function(n) { return (spec.attrs || {})[n] || null; },
    textContent: spec.text || '',
    querySelector: function() { return spec.badge ? node(spec.badge) : null; }
  };
}
var document = {
  querySelector: function() { return dom.button ? node(dom.button) : null; },
  querySelectorAll: function(sel) {
    var list = sel.indexOf('list-title') >= 0 ? (dom.titles || []).map(node)
                                              : new Array(dom.rows || 0);
    list.forEach = Array.prototype.forEach;
    return list;
  }
};
var result = (function() { %(body)s }).apply(null, ['button#roster-button']);
console.log(JSON.stringify(result));
"""


def _run(script, dom):
    src = _HARNESS % {"dom": json.dumps(dom), "body": script}
    out = subprocess.run([NODE, "-e", src], capture_output=True, text=True,
                         timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _badge(aria_label, badge_text=None):
    button = {"attrs": {"aria-label": aria_label}}
    if badge_text is not None:
        button["badge"] = {"text": badge_text}
    return _run(joiner._JS_ROSTER_BADGE_COUNT, {"button": button})


def test_count_at_the_end_of_the_label_is_read():
    assert _badge("Người tham gia, 12") == 12
    assert _badge("Show participants (12)") == 12


def test_a_keyboard_shortcut_is_not_taken_for_the_headcount():
    assert _badge("People (Ctrl+Shift+3)") is None
    assert _badge("People, Ctrl + Shift + 3") is None


def test_shortcut_in_the_label_falls_back_to_the_badge():
    assert _badge("People (Ctrl+Shift+3)", badge_text="27") == 27


def _panel(titles, rows=0):
    return _run(joiner._JS_ROSTER_PANEL_COUNT, {
        "titles": [{"attrs": {"aria-label": t}} for t in titles], "rows": rows})


def test_panel_sections_in_the_call_are_summed():
    assert _panel(["Người trình bày (2)", "Người dự (23)"]) == 25


def test_people_invited_but_not_in_the_call_are_not_counted():
    # As the class leaves, "Others invited" grows by exactly as much as the
    # in-call count falls — summing both keeps the total flat for ever.
    assert _panel(["In this meeting (3)", "Others invited (22)"]) == 3
    assert _panel(["Trong cuộc họp (3)", "Người khác được mời (22)"]) == 3


def test_the_lobby_is_not_counted():
    assert _panel(["In this meeting (10)", "Waiting in lobby (4)"]) == 10


def test_participant_rows_are_the_last_resort():
    assert _panel([], rows=7) == 7
    assert _panel([], rows=0) is None
