"""Fast path for reading the class schedule: Outlook's own JSON calendar API.

The Teams Calendar tab is Outlook embedded in an iframe, and it populates
itself with a single `GetCalendarView` call that returns every event in an
arbitrary date range as JSON — exact ISO timestamps, the subject, and the
Teams thread id of each meeting.

We issue that same call from inside the iframe via execute_async_script, so
the browser attaches whatever credentials the Outlook session already holds;
the bot never handles a token itself. Scraping the rendered calendar (see
scanner._discover_calendar_events) remains as the fallback, because this is
an internal API that Microsoft can change without notice.

Payload shape and headers were taken from a real captured session (2026-09).
"""

import json
from datetime import datetime, timedelta

import runtime as rt
import status

# Sent as the x-owa-urlpostdata header rather than a body — that is how OWA
# itself issues this call.
_JS_GET_CALENDAR_VIEW = r"""
var done = arguments[arguments.length - 1];
var payload = arguments[0];
fetch('/owa/service.svc?action=GetCalendarView&app=Calendar', {
  method: 'POST',
  credentials: 'include',
  headers: {
    'action': 'GetCalendarView',
    'content-type': 'application/json; charset=utf-8',
    'x-req-source': 'Calendar',
    'x-owa-urlpostdata': encodeURIComponent(JSON.stringify(payload))
  }
}).then(function (r) {
  if (!r.ok) { return Promise.reject('HTTP ' + r.status); }
  return r.json();
}).then(function (j) {
  done({ok: true, data: j});
}).catch(function (e) {
  done({ok: false, error: String(e)});
});
"""


def _payload(range_start, range_end, timezone_id):
    return {
        "__type": "GetCalendarViewJsonRequest:#Exchange",
        "Header": {
            "__type": "JsonRequestHeaders:#Exchange",
            "RequestServerVersion": "V2018_01_08",
            "TimeZoneContext": {
                "__type": "TimeZoneContext:#Exchange",
                "TimeZoneDefinition": {
                    "__type": "TimeZoneDefinitionType:#Exchange",
                    "Id": timezone_id,
                },
            },
        },
        "Body": {
            "__type": "GetCalendarViewRequest:#Exchange",
            # The mailbox's default calendar — avoids a second call just to
            # look up the opaque folder id.
            "CalendarId": {
                "__type": "TargetFolderId:#Exchange",
                "BaseFolderId": {
                    "__type": "DistinguishedFolderId:#Exchange",
                    "Id": "calendar",
                },
            },
            "RangeStart": range_start.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "RangeEnd": range_end.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "ClientSupportsIrm": True,
            "OptimizeExtendedPropertyLoading": True,
            # Without this the response carries no Teams thread ids.
            "IncludeSkypeTeamsProperties": True,
        },
    }


def _parse_start(value):
    """'2026-09-09T13:00:00+07:00' → naive local datetime (the rest of the bot
    compares against datetime.now(), which is naive local)."""
    # fromisoformat only learned to read a 'Z' suffix in 3.11, and Outlook may
    # answer in UTC if it ignores our TimeZoneContext.
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _parse_items(items):
    out = []
    for item in items:
        if item.get("IsCancelled"):
            continue
        start_raw = item.get("Start")
        title = (item.get("Subject") or "").strip()
        if not start_raw or not title:
            continue
        try:
            start = _parse_start(start_raw)
        except (ValueError, TypeError):
            continue

        # SkypeTeamsProperties is a JSON *string*; "cid" is the meeting's
        # thread id — for a channel class that is the channel's own thread,
        # which lets the joiner skip hunting through the channel list.
        cid = None
        raw_props = item.get("SkypeTeamsProperties")
        if raw_props:
            try:
                cid = (json.loads(raw_props) or {}).get("cid") or None
            except (ValueError, TypeError):
                cid = None

        out.append({"start": start, "title": title,
                    "source": "calendar", "cid": cid})
    return out


def fetch_calendar_events(days_back=1, days_ahead=14):
    """Return [{start, title, source, cid}] for the coming classes, or None if
    the API could not be used (caller then falls back to scraping the page).

    Must be called with the driver already switched INTO the calendar iframe.
    """
    now = datetime.now()
    payload = _payload(now - timedelta(days=days_back),
                       now + timedelta(days=days_ahead),
                       rt.config.get("calendar_timezone") or "SE Asia Standard Time")
    try:
        rt.browser.set_script_timeout(30)
        res = rt.browser.execute_async_script(_JS_GET_CALENDAR_VIEW, payload)
    except Exception as e:
        status.log(f"API Lịch không dùng được ({str(e).splitlines()[0]}) — "
                   "chuyển sang đọc giao diện.")
        return None

    if not isinstance(res, dict) or not res.get("ok"):
        reason = (res or {}).get("error", "không rõ") if isinstance(res, dict) else "không rõ"
        status.log(f"API Lịch trả lỗi ({reason}) — chuyển sang đọc giao diện.")
        return None

    try:
        items = res["data"]["Body"]["Items"]
    except (KeyError, TypeError):
        status.log("API Lịch trả dữ liệu lạ — chuyển sang đọc giao diện.")
        return None

    events = _parse_items(items or [])
    if items and not events:
        # The response carried events but none survived parsing — treat that as
        # "the API shape changed under us" and let the caller scrape instead.
        # Returning [] here would look like "no classes today" and the bot
        # would quietly never join anything.
        status.log("API Lịch trả về sự kiện nhưng không đọc được buổi nào — "
                   "chuyển sang đọc giao diện.")
        return None

    status.log(f"Đọc lịch qua API: {len(events)} buổi học "
               f"(trong {days_back + days_ahead} ngày).")
    return events
