"""Discord webhook notifications via a plain HTTP POST.

Replaces the discord.py dependency: a webhook message is just JSON POSTed to
the webhook URL, and dropping discord.py removes aiohttp & friends from the
PyInstaller bundle (~30 MB smaller, fewer install failures)."""

from datetime import datetime

import requests

import runtime as rt


def discord_notification(title, description):
    url = rt.config.get("discord_webhook_url", "")
    if not url:
        return
    payload = {
        "embeds": [{
            "title": str(title),
            "description": str(description),
            "color": 0x0011FF,
            "author": {"name": "Ms-Teams-Auto-Joiner-Bot"},
            "footer": {"text": (f"\nTime: [{datetime.now():%Y:%m:%d-%H:%M:%S}]"
                                f"\nlogin-id: {rt.config.get('email', '')}")},
        }]
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        print("Failed to send discord notification")
