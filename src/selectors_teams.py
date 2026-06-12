"""Every CSS selector and JS snippet used against new Teams / Outlook.

This is THE file to edit when Microsoft changes the Teams UI. Selectors were
derived from live DOM dumps (2026-05/06) and verified on a real account —
change them only against a fresh dump (see tools/inspect_teams.py)."""

uuid_regex = r"\b[0-9a-f]{8}\b-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-\b[0-9a-f]{12}\b"

# ── New-Teams selectors (all data-tid / data-inp / stable IDs) ────────────────
SEL_PAGE_READY      = "[data-tid='all-phased-rendering-complete']"
# App-bar buttons: match by the Teams app GUID first (fixed, language-independent),
# then fall back to English/Vietnamese aria-labels for older/other tenants.
SEL_TEAMS_BTN       = ("button[id='2a84919f-59d8-4441-a975-2a8c2643b741'],"
                       "button[aria-label^='Teams'],button[aria-label^='Nhóm']")
SEL_CALENDAR_BTN    = ("button[id='ef56c0de-36fc-4ef8-b417-3d82ba9d073c'],"
                       "button[aria-label^='Calendar'],button[aria-label^='Lịch']")
SEL_TEAMS_GRID      = "[data-tid='teams-grid-view']"
SEL_TEAM_CARD       = "[data-tid$='-team-card']"
SEL_CHANNEL_ITEM    = "[data-tid='channel-list-item']"
SEL_CH_JOIN_BTN     = "button[data-tid='pre-state-schedule-meeting-join-button']"
SEL_MEETING_BANNER  = "[data-tid='pre-state-schedule-meeting-banner-renderer']"
SEL_CAL_IFRAME      = "iframe[data-tid='hwc-iframe'], iframe[title='Calendar']"
SEL_PREJOIN_SCREEN  = "[data-tid='calling-prejoin-screen']"
SEL_PREJOIN_JOIN    = "button[data-tid='prejoin-join-button']"
SEL_TOGGLE_VIDEO    = "input[data-tid='toggle-video']"
SEL_TOGGLE_MUTE     = "input[data-tid='toggle-mute']"
SEL_INCALL_VIDEO    = "button#video-button"
SEL_INCALL_MIC      = "button#microphone-button"
SEL_HANGUP          = "button[data-tid='hangup-main-btn']"
SEL_ROSTER          = "button#roster-button"
SEL_CALL_DURATION   = "[data-tid='call-duration']"

# ── JS run INSIDE the calendar (Outlook) iframe ───────────────────────────────
# new Teams Calendar is Outlook embedded in an iframe. Teams-meeting events have
# an aria-label containing "Microsoft Teams". Clicking an event opens a peek with
# a "Join" button (visible text exactly "Join").
_JS_CAL_EVENTS = r"""
var out=[], seen={};
var els=document.querySelectorAll('button,[role="button"],div[role="button"]');
for(var i=0;i<els.length;i++){
  var al=els[i].getAttribute('aria-label')||'';
  if(al.toLowerCase().indexOf('microsoft teams')>=0 && !seen[al]){seen[al]=1;out.push(al);}
}
return out;
"""

_JS_CLICK_EVENT = r"""
// Click a calendar event. `want` is the event title; an event's aria-label
// reads "<title>, <time> đến <time>, <date>, …", so match exact, then by the
// title as a prefix, then anywhere.
var want=arguments[0];
var els=document.querySelectorAll('button,[role="button"],div[role="button"],[aria-label]');
for(var i=0;i<els.length;i++){if((els[i].getAttribute('aria-label')||'')===want){els[i].click();return true;}}
for(var i=0;i<els.length;i++){var al=els[i].getAttribute('aria-label')||'';if(al && want && al.indexOf(want)===0){els[i].click();return true;}}
for(var i=0;i<els.length;i++){var al=els[i].getAttribute('aria-label')||'';if(al && want && al.indexOf(want)>=0){els[i].click();return true;}}
return false;
"""

_JS_CLICK_JOIN = r"""
// Click the calendar peek's Join button. The real one has aria-label
// "Tham gia cuộc họp Teams" (or "Join …meeting"); its visible text is often just
// an icon. We must NOT hit the toolbar's "Tham gia bằng ID" (Join with an ID).
function clean(s){return (s||'').replace(/[-]/g,'').replace(/\s+/g,' ').trim().toLowerCase();}
var els=document.querySelectorAll('button,[role="button"],a,div[role="button"]');
// 1) Preferred: the explicit "join the Teams meeting" button, by aria-label.
for(var i=0;i<els.length;i++){
  var al=clean(els[i].getAttribute('aria-label'));
  if(al.indexOf('tham gia cuộc họp')>=0 || (al.indexOf('join')>=0 && al.indexOf('meeting')>=0)){
    els[i].click();return true;}
}
// 2) Fallback: a control whose label is exactly "Tham gia" / "Join".
for(var i=0;i<els.length;i++){
  var t=clean(els[i].innerText||els[i].textContent);
  var al2=clean(els[i].getAttribute('aria-label'));
  if(t==='tham gia'||t==='join'||al2==='tham gia'||al2==='join'){els[i].click();return true;}
}
return false;
"""

# Every aria-label on the calendar that carries a clock time (HH:MM).
_CAL_EVENTS_JS = r"""
var out=[], seen={};
document.querySelectorAll('[aria-label]').forEach(function(e){
  var al=e.getAttribute('aria-label')||'';
  if(/\d{1,2}:\d{2}/.test(al) && al.length>12 && !seen[al]){seen[al]=1; out.push(al.slice(0,220));}
});
return out.slice(0,120);
"""

# Calendar aria-labels that are markers, not real events.
_CAL_SKIP = ("ngoài giờ làm việc", "thời gian hiện tại", "kế hoạch công việc",
             "dạng xem lịch")
