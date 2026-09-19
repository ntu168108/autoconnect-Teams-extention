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
import time
from datetime import datetime, timedelta

import runtime as rt
import status

# OWA keeps its Outlook token in JavaScript memory, not in web storage — a
# scan of localStorage/sessionStorage on a live session turned up no JWT at
# all. So rather than hunting for where it is kept, we watch OWA use it: wrap
# fetch and XMLHttpRequest, and keep the Bearer value off any request the page
# makes to its own service. Idempotent, and left in place so that later scans
# find a token already waiting.
_JS_INSTALL_PROBE = r"""
if (window.__tajProbe) { return 'already'; }
window.__tajProbe = {token: null};

function keep(value) {
  try {
    var v = String(value || '');
    if (v.slice(0, 7).toLowerCase() === 'bearer ') {
      window.__tajProbe.token = v.slice(7);
    }
  } catch (e) {}
}

function scanHeaders(h) {
  try {
    if (!h) { return; }
    if (typeof h.get === 'function') { keep(h.get('authorization')); return; }
    if (Array.isArray(h)) {
      h.forEach(function (pair) {
        if (pair && String(pair[0]).toLowerCase() === 'authorization') { keep(pair[1]); }
      });
      return;
    }
    Object.keys(h).forEach(function (k) {
      if (k.toLowerCase() === 'authorization') { keep(h[k]); }
    });
  } catch (e) {}
}

var origFetch = window.fetch;
window.fetch = function (input, init) {
  try {
    if (init && init.headers) { scanHeaders(init.headers); }
    else if (input && input.headers) { scanHeaders(input.headers); }
  } catch (e) {}
  return origFetch.apply(this, arguments);
};

var origSet = XMLHttpRequest.prototype.setRequestHeader;
XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
  try {
    if (String(name).toLowerCase() === 'authorization') { keep(value); }
  } catch (e) {}
  return origSet.apply(this, arguments);
};

return 'installed';
"""

_JS_READ_PROBE = "return (window.__tajProbe && window.__tajProbe.token) || null;"


# The payload goes in the x-owa-urlpostdata header rather than a body — that
# is how OWA itself issues this call.
#
# Auth: the Outlook iframe is a THIRD PARTY inside teams.cloud.microsoft, so
# its cookies are not sent and `credentials: 'include'` alone earns an HTTP
# 401. OWA therefore carries a bearer token, which it keeps in page storage.
# We do not know the storage key (it is a minified MSAL-style cache and
# changes between builds), so instead we scan every stored value for anything
# shaped like a JWT and keep the one whose audience is Outlook and which has
# not expired. That survives a key rename; if Microsoft ever stops storing it
# where scripts can read it, we simply find nothing and fall back to scraping.
_JS_GET_CALENDAR_VIEW = r"""
var done = arguments[arguments.length - 1];
var payload = arguments[0];

function decodeJwt(tok) {
  try {
    var p = tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    while (p.length % 4) { p += '='; }
    return JSON.parse(atob(p));
  } catch (e) { return null; }
}

function findOutlookToken() {
  var jwt = /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+/g;
  var now = Math.floor(Date.now() / 1000);
  var best = null, auds = {};
  [localStorage, sessionStorage].forEach(function (store) {
    try {
      for (var i = 0; i < store.length; i++) {
        var raw = store.getItem(store.key(i)) || '';
        var hits = raw.match(jwt);
        if (!hits) { continue; }
        for (var h = 0; h < hits.length; h++) {
          var body = decodeJwt(hits[h]);
          if (!body || !body.aud) { continue; }
          auds[body.aud] = 1;
          if (String(body.aud).indexOf('outlook.office.com') < 0) { continue; }
          if (body.exp && body.exp <= now + 60) { continue; }
          // Prefer the one that stays valid longest.
          if (!best || (body.exp || 0) > best.exp) {
            best = {token: hits[h], exp: body.exp || 0};
          }
        }
      }
    } catch (e) {}
  });
  return {token: best && best.token, auds: Object.keys(auds)};
}

// A token captured from OWA's own traffic beats anything we dig out of
// storage: it is the exact credential the page is using right now.
var captured = arguments[1] || null;
var found = captured ? {token: captured, auds: ['(bắt được từ OWA)']}
                     : findOutlookToken();
var headers = {
  'action': 'GetCalendarView',
  'content-type': 'application/json; charset=utf-8',
  'x-req-source': 'Calendar',
  'x-owa-urlpostdata': encodeURIComponent(JSON.stringify(payload))
};
if (found.token) { headers['authorization'] = 'Bearer ' + found.token; }

fetch('/owa/service.svc?action=GetCalendarView&app=Calendar', {
  method: 'POST',
  credentials: 'include',
  headers: headers
}).then(function (r) {
  if (!r.ok) { return Promise.reject('HTTP ' + r.status); }
  return r.json();
}).then(function (j) {
  done({ok: true, data: j, hadToken: !!found.token});
}).catch(function (e) {
  done({ok: false, error: String(e), hadToken: !!found.token,
        auds: found.auds.slice(0, 12)});
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
        if not start_raw:
            continue
        # An event with no subject is still a real class to join — Outlook just
        # shows it under this placeholder, so use the same wording rather than
        # dropping the event. (The scraped path always had a title because it
        # reads the label Outlook renders, so only this path lost them.)
        title = (item.get("Subject") or "").strip() or "(Không có chủ đề)"
        try:
            start = _parse_start(start_raw)
        except (ValueError, TypeError):
            continue

        # End lets the scheduler tell a class that is still running from one
        # that has already finished — scraping the page never gave us this.
        try:
            end = _parse_start(item["End"])
        except (KeyError, ValueError, TypeError):
            end = None

        # SkypeTeamsProperties is a JSON *string*. "cid" is the meeting's Teams
        # thread id and "rid" its message id — together they form the meeting's
        # own join link, which lets the joiner open the class directly instead
        # of hunting for its tile in the rendered calendar.
        cid = rid = None
        raw_props = item.get("SkypeTeamsProperties")
        if raw_props:
            try:
                props = json.loads(raw_props) or {}
                cid = props.get("cid") or None
                rid = props.get("rid") or None
            except (ValueError, TypeError):
                cid = rid = None

        out.append({"start": start, "end": end, "title": title,
                    "source": "calendar", "cid": cid, "rid": rid})
    return out


def _capture_token(wait_seconds):
    """Install the probe and hand back the Bearer token OWA is using, if we
    manage to see one. Returns None when nothing was captured in time.

    The probe survives between scans, so a run that misses the token now
    usually has one ready by the next scan — OWA polls its own service while
    the calendar sits open."""
    try:
        state = rt.browser.execute_script(_JS_INSTALL_PROBE)
    except Exception:
        return None

    deadline = time.time() + max(wait_seconds, 0)
    while True:
        try:
            token = rt.browser.execute_script(_JS_READ_PROBE)
        except Exception:
            return None
        if token:
            return token
        # Only worth waiting the first time: if the probe has been sitting
        # there since an earlier scan and still has nothing, waiting longer
        # this cycle will not change that.
        if state == "already" or time.time() >= deadline:
            return None
        time.sleep(1)


def fetch_calendar_events(days_back=1, days_ahead=14):
    """Return [{start, end, title, source, cid, rid}] for the coming classes,
    or None if the API could not be used (caller then falls back to scraping).

    Must be called with the driver already switched INTO the calendar iframe.
    """
    now = datetime.now()
    payload = _payload(now - timedelta(days=days_back),
                       now + timedelta(days=days_ahead),
                       rt.config.get("calendar_timezone") or "SE Asia Standard Time")
    token = _capture_token(int(rt.config.get("token_wait_seconds", 10) or 0))
    try:
        rt.browser.set_script_timeout(30)
        res = rt.browser.execute_async_script(_JS_GET_CALENDAR_VIEW, payload, token)
    except Exception as e:
        status.log(f"API Lịch không dùng được ({str(e).splitlines()[0]}) — "
                   "chuyển sang đọc giao diện.")
        return None

    if not isinstance(res, dict) or not res.get("ok"):
        if not isinstance(res, dict):
            status.log("API Lịch trả lỗi (không rõ) — chuyển sang đọc giao diện.")
            return None
        reason = res.get("error", "không rõ")
        if not res.get("hadToken"):
            # Say which audiences we did find: that is what tells us whether
            # the Outlook token moved somewhere a script cannot read, or was
            # simply not issued yet for this session.
            auds = ", ".join(res.get("auds") or []) or "không thấy token nào"
            status.log(f"API Lịch trả lỗi ({reason}) — không tìm thấy token Outlook "
                       f"trong trang [{auds}]. Chuyển sang đọc giao diện.")
        else:
            status.log(f"API Lịch trả lỗi ({reason}) dù đã gắn token — "
                       "chuyển sang đọc giao diện.")
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
