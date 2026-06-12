import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import notify
import runtime as rt


def test_no_url_no_post(monkeypatch):
    rt.config = {}
    called = []
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: called.append(a))
    notify.discord_notification("t", "d")
    assert called == []


def test_posts_embed(monkeypatch):
    rt.config = {"discord_webhook_url": "https://discord.test/hook", "email": "a@b.c"}
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json

        class R:
            status_code = 204
        return R()

    monkeypatch.setattr(notify.requests, "post", fake_post)
    notify.discord_notification("Joined meeting", "Toán")
    assert captured["url"] == "https://discord.test/hook"
    embed = captured["json"]["embeds"][0]
    assert embed["title"] == "Joined meeting"
    assert embed["description"] == "Toán"
    assert "a@b.c" in embed["footer"]["text"]


def test_post_errors_swallowed(monkeypatch):
    rt.config = {"discord_webhook_url": "https://discord.test/hook"}

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify.requests, "post", boom)
    notify.discord_notification("t", "d")  # must not raise
