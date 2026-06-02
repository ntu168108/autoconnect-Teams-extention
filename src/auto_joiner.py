import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from threading import Timer

# When run as  python src/auto_joiner.py  from the repo root, the working
# directory is the repo root — that's where config.json lives.  Store the
# absolute root path once so every relative open() goes to the right place.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from getpass import getpass

from discord import SyncWebhook, Embed

# Windows consoles often default to a legacy code page (cp1252) that cannot
# encode Vietnamese characters in team / meeting names, which crashes print().
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Globals ───────────────────────────────────────────────────────────────────
browser: webdriver.Chrome = None
total_members = None
config = None
meetings = []
current_meeting = None
already_joined_ids = []
hangup_thread: Timer = None
mode = 3
channel_to_team = {}          # {channel_thread_id: team_thread_id}
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
function clean(s){return (s||'').replace(/[-]/g,'').replace(/\s+/g,' ').trim().toLowerCase();}
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


# ── Data classes ──────────────────────────────────────────────────────────────

class Channel:
    def __init__(self, name, c_id, blacklisted=False, has_meeting=False):
        self.name = name
        self.c_id = c_id
        self.blacklisted = blacklisted
        self.has_meeting = has_meeting

    def __str__(self):
        return (self.name
                + (" [BLACKLISTED]" if self.blacklisted else "")
                + (" [MEETING]"    if self.has_meeting  else ""))


class Team:
    def __init__(self, name, t_id, channels=None):
        self.name = name
        self.t_id = t_id
        self.channels = channels if channels is not None else []

    def __str__(self):
        ch_str = '\n\t'.join(str(c) for c in self.channels)
        return f"{self.name}\n\t{ch_str}"

    def check_blacklist(self):
        blacklist = config.get('blacklist', [])
        bl_item = next((b for b in blacklist if b['team_name'] == self.name), None)
        if bl_item is None:
            return
        if len(bl_item['channel_names']) == 0:
            for ch in self.channels:
                ch.blacklisted = True
        else:
            for ch in self.channels:
                if ch.name in bl_item['channel_names']:
                    ch.blacklisted = True


class Meeting:
    def __init__(self, m_id, time_started, title,
                 calendar_meeting=False, channel_id=None, team_id=None):
        self.m_id = m_id
        self.time_started = time_started
        self.title = title
        self.calendar_meeting = calendar_meeting
        self.calendar_blacklisted = calendar_meeting and self._check_blacklist_calendar()
        self.channel_id = channel_id
        self.team_id = team_id

    def _check_blacklist_calendar(self):
        if config.get('blacklist_meeting_re'):
            return bool(re.search(config['blacklist_meeting_re'], self.title))
        return False

    def __str__(self):
        return (f"\t{self.title} {self.time_started}"
                + (" [Calendar]" if self.calendar_meeting else " [Channel]")
                + (" [BLACKLISTED]" if self.calendar_blacklisted else ""))


# ── Config / browser setup ────────────────────────────────────────────────────

def load_config():
    global config
    with open(os.path.join(_ROOT, 'config.json'), encoding='utf-8') as f:
        config = json.load(f)


def init_browser():
    global browser

    if config.get('chrome_type') == "msedge":
        chrome_options = webdriver.EdgeOptions()
    else:
        chrome_options = webdriver.ChromeOptions()

    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--use-fake-ui-for-media-stream')
    chrome_options.add_experimental_option('prefs', {
        'credentials_enable_service': False,
        'profile.default_content_setting_values.media_stream_mic': 1,
        'profile.default_content_setting_values.media_stream_camera': 1,
        'profile.default_content_setting_values.geolocation': 1,
        'profile.default_content_setting_values.notifications': 1,
        'profile': {'password_manager_enabled': False},
    })
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])

    if config.get('headless'):
        chrome_options.add_argument('--headless=new')
        print("Enabled headless mode")

    if config.get('mute_audio'):
        chrome_options.add_argument("--mute-audio")

    # Selenium 4.6+ bundles Selenium Manager — no explicit driver path needed.
    if config.get('chrome_type') == "msedge":
        browser = webdriver.Edge(options=chrome_options)
    else:
        if config.get('chrome_type') == "chromium" and config.get("chromium_binary"):
            chrome_options.binary_location = config["chromium_binary"]
        browser = webdriver.Chrome(options=chrome_options)

    w = browser.get_window_size()
    if w['width'] < 1200:
        browser.set_window_size(1200, w['height'])
        print("Resized window width")
    if w['height'] < 850:
        browser.set_window_size(w['width'], 850)
        print("Resized window height")


# ── Utilities ─────────────────────────────────────────────────────────────────

def discord_notification(title, description):
    url = config.get('discord_webhook_url', '')
    if not url:
        return
    try:
        webhook = SyncWebhook.from_url(url)
        embed = Embed(title=str(title), description=str(description), colour=0x0011FF)
        embed.set_author(name="Ms-Teams-Auto-Joiner-Bot")
        embed.set_footer(
            text=f"\nTime: [{datetime.now():%Y:%m:%d-%H:%M:%S}]\nlogin-id: {config.get('email','')}")
        webhook.send(embed=embed)
    except Exception:
        print("Failed to send discord notification")


def wait_until_found(sel, timeout, print_error=True):
    try:
        WebDriverWait(browser, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
        return browser.find_element(By.CSS_SELECTOR, sel)
    except exceptions.TimeoutException:
        if print_error:
            print(f"Timeout waiting for element: {sel}")
            discord_notification("Timeout error", sel)
        return None


def wait_present(sel, timeout):
    """Like wait_until_found but only requires the element to exist in the DOM,
    not to be visible. Needed for Fluent UI toggle inputs (the real <input> is
    visually hidden with opacity:0, so a visibility check never matches)."""
    try:
        WebDriverWait(browser, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
        return browser.find_element(By.CSS_SELECTOR, sel)
    except exceptions.TimeoutException:
        return None


# ── Tab navigation ────────────────────────────────────────────────────────────

def switch_to_teams_tab():
    btn = wait_until_found(SEL_TEAMS_BTN, 5, print_error=False)
    if btn:
        browser.execute_script("arguments[0].click()", btn)
        time.sleep(1)


def switch_to_calendar_tab():
    btn = wait_until_found(SEL_CALENDAR_BTN, 5, print_error=False)
    if btn:
        browser.execute_script("arguments[0].click()", btn)
        time.sleep(1)


# ── Organisation switcher ─────────────────────────────────────────────────────

def change_organisation(org_num):
    # New Teams profile button id: idna-me-control-avatar-trigger
    profile_button = wait_until_found("button#idna-me-control-avatar-trigger", 20)
    if profile_button is None:
        profile_button = wait_until_found("button#personDropdown", 10)
    if profile_button is None:
        print("Could not find profile button while changing organisation")
        return

    profile_button.click()

    change_org_button = wait_until_found(
        f"li[aria-posinset='{org_num + 1}']", 10)
    if change_org_button is None:
        print("Could not find organisation button")
        return

    try:
        change_org_button.find_element(By.CSS_SELECTOR, "button.active")
    except exceptions.NoSuchElementException:
        pass
    else:
        print("Organisation not changed (already selected)")
        return

    change_org_button.click()
    time.sleep(5)


# ── Teams / channel scanning ──────────────────────────────────────────────────

def get_all_teams():
    """Return a flat list of Team objects from the Teams grid view."""
    switch_to_teams_tab()
    if wait_until_found(SEL_TEAMS_GRID, 10, print_error=False) is None:
        print("Teams grid not found — is the Teams tab showing grid view?")
        return []

    cards = browser.find_elements(By.CSS_SELECTOR, SEL_TEAM_CARD)
    teams = []
    for card in cards:
        tid_attr = card.get_attribute("data-tid") or ""
        thread_id = tid_attr.replace("-team-card", "")
        if not thread_id:
            continue
        aria = card.get_attribute("aria-label") or ""
        # aria-label is "TEAM_NAME Team X of Y" (EN) or "... Nhóm X của Y" (VI)
        # — strip the trailing position suffix in either language.
        name = re.sub(r'\s+(Team|Nhóm)\s+\d+\s+(of|của)\s+\d+\s*$', '', aria).strip()
        if not name:
            name = thread_id
        teams.append(Team(name, thread_id))
    return teams


def _get_channels_from_sidebar(team):
    """
    Read the channel sidebar after navigating into a team.
    Returns list of Channel objects and updates channel_to_team mapping.
    """
    global channel_to_team
    items = browser.find_elements(By.CSS_SELECTOR, SEL_CHANNEL_ITEM)
    channels = []
    for item in items:
        sid = item.get_attribute("data-sid") or ""
        if not sid.startswith("channel-shown-"):
            continue
        c_id = sid.replace("channel-shown-", "")
        try:
            text_el = item.find_element(
                By.CSS_SELECTOR, "[data-tid^='channel-list-item-text-']")
            name = text_el.text.strip() or c_id
        except exceptions.NoSuchElementException:
            name = c_id
        channels.append(Channel(name, c_id))
        channel_to_team[c_id] = team.t_id
    return channels


def get_meetings(teams):
    """
    For each team, navigate to it, collect channels, then check each channel
    for an active/upcoming meeting join button.
    """
    global meetings

    for team in teams:
        # Navigate to team card
        switch_to_teams_tab()
        card = wait_until_found(
            f"[data-tid='{team.t_id}-team-card']", 5, print_error=False)
        if card is None:
            continue
        browser.execute_script("arguments[0].click()", card)
        time.sleep(2)

        # Collect channels from sidebar (element refs go stale after clicks)
        channels = _get_channels_from_sidebar(team)
        team.channels = channels
        team.check_blacklist()

        for ch in team.channels:
            if ch.blacklisted:
                continue

            # Navigate to channel
            ch_btn = wait_until_found(
                f"[data-tid='channel-list-item-text-{ch.c_id}']",
                3, print_error=False)
            if ch_btn is None:
                continue
            try:
                browser.execute_script("arguments[0].click()", ch_btn)
                time.sleep(2)
            except Exception:
                continue

            # Check for an active meeting join button
            if wait_until_found(SEL_CH_JOIN_BTN, 3, print_error=False) is None:
                continue

            m_id = f"channel:{ch.c_id}"
            if m_id in already_joined_ids:
                continue

            title = f"{team.name} → {ch.name}"
            try:
                banner = browser.find_element(By.CSS_SELECTOR, SEL_MEETING_BANNER)
                aria = banner.get_attribute("aria-label") or ""
                # "Scheduled meeting. TITLE. DATE..."
                parts = [p.strip() for p in aria.split(".") if p.strip()]
                if len(parts) >= 2:
                    title = parts[1]
            except exceptions.NoSuchElementException:
                pass

            meetings.append(Meeting(
                m_id=m_id,
                time_started=int(time.time()),
                title=title,
                calendar_meeting=False,
                channel_id=ch.c_id,
                team_id=team.t_id,
            ))
            ch.has_meeting = True

    # Return to teams grid after full scan
    switch_to_teams_tab()


def get_calendar_meetings():
    """Scan the Outlook calendar (embedded iframe) for Teams meeting events."""
    global meetings

    switch_to_calendar_tab()
    time.sleep(4)

    iframe = wait_until_found(SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        print("Calendar iframe not found (is the Calendar tab open?)")
        return

    # The Outlook calendar inside the iframe renders its events asynchronously,
    # so poll until events appear (or the calendar is loaded with none).
    browser.switch_to.frame(iframe)
    labels = []
    try:
        deadline = time.time() + 18
        ready_since = None
        while time.time() < deadline:
            try:
                n = browser.execute_script(
                    'return document.querySelectorAll(\'button,[role="button"]\').length;') or 0
                labels = browser.execute_script(_JS_CAL_EVENTS) or []
            except Exception:
                n, labels = 0, []
            if labels:
                break
            if n > 25:               # OWA calendar grid has rendered
                if ready_since is None:
                    ready_since = time.time()
                elif time.time() - ready_since > 4:   # loaded, still no events
                    break
            time.sleep(1.5)
    finally:
        browser.switch_to.default_content()

    for label in labels:
        # aria-label looks like "TITLE, 12:30 AM to 1:00 AM, Monday, ... , Microsoft Teams ..."
        title = label.split(",")[0].strip() or "Calendar meeting"
        m_id = "calendar:" + label
        if m_id in already_joined_ids:
            continue
        mtg = Meeting(
            m_id=m_id,
            time_started=int(time.time()),
            title=title,
            calendar_meeting=True,
        )
        mtg.cal_label = label
        meetings.append(mtg)


# ── Decision logic ────────────────────────────────────────────────────────────

def decide_meeting():
    global meetings

    meetings = [m for m in meetings if not m.calendar_blacklisted]
    if not meetings:
        return None

    meetings.sort(key=lambda x: x.time_started, reverse=True)
    newest_time = meetings[0].time_started

    newest = [m for m in meetings if m.time_started >= newest_time]

    candidate = newest[0]
    if (current_meeting is None
            or candidate.time_started > current_meeting.time_started
            or candidate.m_id != current_meeting.m_id) \
            and candidate.m_id not in already_joined_ids:
        return candidate
    return None


# ── Pre-join helpers ──────────────────────────────────────────────────────────

def _prejoin_turn_off_camera():
    """
    Camera toggle is a Fluent UI Switch <input> (visually hidden -> use presence).
    Camera is ON when aria-checked == "true", or the title offers to turn it OFF.
    """
    inp = wait_present(SEL_TOGGLE_VIDEO, 6)
    if inp is None:
        return
    title = (inp.get_attribute("title") or "").lower()
    checked = (inp.get_attribute("aria-checked") or "").lower()
    camera_on = (checked == "true"
                 or "turn camera off" in title or "tắt camera" in title)
    if camera_on:
        browser.execute_script("arguments[0].click()", inp)
        print("Camera turned off")


def _prejoin_mute_mic():
    """
    Mic toggle is a Fluent UI Switch <input> (visually hidden -> use presence).
    Mic is ON (unmuted) when aria-checked == "true", or the title offers to MUTE.
    """
    inp = wait_present(SEL_TOGGLE_MUTE, 6)
    if inp is None:
        return
    title = (inp.get_attribute("title") or "").lower()
    checked = (inp.get_attribute("aria-checked") or "").lower()
    offers_mute = "mute mic" in title or "tắt micrô" in title or "tắt tiếng" in title
    offers_unmute = "unmute" in title or "bật micrô" in title or "bật tiếng" in title
    mic_on = (checked == "true" or offers_mute) and not offers_unmute
    if mic_on:
        browser.execute_script("arguments[0].click()", inp)
        print("Microphone muted")


# ── Joining ───────────────────────────────────────────────────────────────────

def _open_calendar_meeting(meeting):
    """Open the event peek in the calendar iframe and click its Join button.

    Returns True if Join was clicked (the Teams pre-join screen should then
    appear in the main app). Always returns with the driver on default content.
    """
    switch_to_calendar_tab()
    time.sleep(3)

    iframe = wait_until_found(SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        print("Calendar iframe not found")
        return False

    browser.switch_to.frame(iframe)
    try:
        time.sleep(1)
        label = getattr(meeting, "cal_label", "") or meeting.title
        if not browser.execute_script(_JS_CLICK_EVENT, label):
            print(f"Could not open calendar event: {meeting.title}")
            return False
        # The peek/callout renders asynchronously — poll up to ~14s for its
        # "Tham gia cuộc họp Teams" button instead of a single fixed wait.
        time.sleep(2)
        for _ in range(6):
            if browser.execute_script(_JS_CLICK_JOIN):
                return True
            time.sleep(2)
        print("Could not find the Join button in the calendar peek")
        return False
    finally:
        browser.switch_to.default_content()


def _open_meeting_chat():
    """Open the IN-MEETING chat panel (the side panel, NOT the app-bar Chat tab).

    The only safe way to open meeting chat is via the toolbar inside the meeting
    (data-tid='ubar-horizontal-middle-end'). We wait up to 15 s for that toolbar
    to appear, then find the Chat button within it. We never fall back to a bare
    'button[aria-label="Chat"]' search because that catches the left app-bar button
    which minimises the meeting window and opens personal chat.
    """
    # Wait for the in-meeting toolbar to be present first
    toolbar = wait_present("[data-tid='ubar-horizontal-middle-end']", 15)
    if toolbar is None:
        print("In-meeting toolbar not found — cannot open meeting chat")
        return False

    # Find the Chat button *inside* the toolbar only
    try:
        btn = toolbar.find_element(By.CSS_SELECTOR, "button[aria-label^='Chat']")
    except exceptions.NoSuchElementException:
        print("Chat button not found inside meeting toolbar")
        return False

    browser.execute_script("arguments[0].click()", btn)
    time.sleep(2)
    return True


def join_meeting(meeting):
    global hangup_thread, current_meeting, already_joined_ids

    hangup()

    # ── Reach the pre-join screen ──────────────────────────────────────────
    if meeting.calendar_meeting:
        if not _open_calendar_meeting(meeting):
            return
        # _open_calendar_meeting already clicked Join inside the iframe.
    else:
        # Navigate to the right team then the right channel
        switch_to_teams_tab()
        time.sleep(1)

        team_id = meeting.team_id or channel_to_team.get(meeting.channel_id)
        if team_id:
            card = wait_until_found(
                f"[data-tid='{team_id}-team-card']", 5, print_error=False)
            if card:
                browser.execute_script("arguments[0].click()", card)
                time.sleep(2)

        ch_btn = wait_until_found(
            f"[data-tid='channel-list-item-text-{meeting.channel_id}']",
            5, print_error=False)
        if ch_btn:
            browser.execute_script("arguments[0].click()", ch_btn)
            time.sleep(2)

        join_btn = wait_until_found(SEL_CH_JOIN_BTN, 10)
        if join_btn is None:
            print(f"Could not find join button for: {meeting.title}")
            return
        browser.execute_script("arguments[0].click()", join_btn)

    # ── Pre-join screen ────────────────────────────────────────────────────
    if wait_until_found(SEL_PREJOIN_SCREEN, 30) is None:
        print("Pre-join screen did not appear")
        return

    _prejoin_turn_off_camera()
    _prejoin_mute_mic()

    # Optional random delay before joining
    if 'random_delay' in config:
        rd = config['random_delay']
        if isinstance(rd, bool):
            delay = random.randrange(10, 31) if rd else 0
        else:
            delay = random.randrange(rd[0], rd[1] + 1)
        if delay > 0:
            print(f"Waiting {delay}s before joining…")
            time.sleep(delay)

    join_now = wait_until_found(SEL_PREJOIN_JOIN, 10)
    if join_now is None:
        return
    browser.execute_script("arguments[0].click()", join_now)

    current_meeting = meeting
    already_joined_ids.append(meeting.m_id)

    # Optional join message. new Teams uses a CKEditor message box, so the text
    # must be TYPED (send_keys) — setting textContent directly does not update
    # CKEditor's model, so the message would send empty / not at all.
    if config.get("join_message"):
        time.sleep(3)
        try:
            if not _open_meeting_chat():
                print("Could not open the in-meeting chat")
            else:
                box = wait_until_found("div[data-tid='ckeditor']", 8, print_error=False)
                if box is None:
                    print("Could not find the chat message box")
                else:
                    box.click()
                    box.send_keys(config["join_message"])
                    time.sleep(1)
                    # The send button is visually hidden until text is typed, so
                    # use wait_present (DOM presence) not wait_until_found (visibility).
                    # Meeting chat = 'newMessageCommands-send';
                    # existing chat  = 'sendMessageCommands-send'. Try both.
                    send_btn = (
                        wait_present("button[data-tid='newMessageCommands-send']", 4)
                        or wait_present("button[data-tid='sendMessageCommands-send']", 2)
                    )
                    if send_btn is not None:
                        browser.execute_script("arguments[0].click()", send_btn)
                    else:
                        # Last resort: Ctrl+Enter (Teams sends on Ctrl+Enter, not plain Enter)
                        box.send_keys(Keys.CONTROL, Keys.ENTER)
                    print(f'Sent message: {config["join_message"]}')
                    discord_notification("Sent message", config["join_message"])
        except Exception as e:
            print(f"Failed to send join message: {e}")

    print(f"Joined meeting: {meeting.title}")
    discord_notification("Joined meeting", meeting.title)

    if config.get('auto_leave_after_min', -1) > 0:
        hangup_thread = Timer(config['auto_leave_after_min'] * 60, hangup)
        hangup_thread.start()


# ── In-call helpers ───────────────────────────────────────────────────────────

def get_meeting_members():
    """
    Count participants in the current meeting via the People panel.
    Returns total count, or None if unavailable.

    NOTE: The exact roster-panel selectors for new Teams have not been
    confirmed yet (a 'trong-hop' DOM dump with People panel open is needed).
    Currently falls back to None so the main loop still runs.
    """
    global current_meeting

    # If the hangup button is gone, meeting ended
    if wait_until_found(SEL_HANGUP, 3, print_error=False) is None:
        current_meeting = None
        print("No longer in any meeting")
        return None

    try:
        browser.execute_script("document.getElementById('roster-button').click()")
    except exceptions.JavascriptException:
        print("Failed to open People panel")
        return None

    time.sleep(2)

    # Try old-style selector first (might still match in new Teams)
    participants_elem = wait_until_found(
        "calling-roster-section[section-key='participantsInCall'] .roster-list-title",
        2, print_error=False)
    attendees_elem = wait_until_found(
        "calling-roster-section[section-key='attendeesInMeeting'] .roster-list-title",
        2, print_error=False)

    count = None
    if participants_elem is not None or attendees_elem is not None:
        participants = ([int(s) for s in (participants_elem.get_attribute("aria-label") or "").split() if s.isdigit()]
                        if participants_elem else [0])
        attendees    = ([int(s) for s in (attendees_elem.get_attribute("aria-label") or "").split() if s.isdigit()]
                        if attendees_elem else [0])
        count = sum(participants + attendees)

    # Close People panel
    try:
        browser.execute_script("document.getElementById('roster-button').click()")
    except exceptions.JavascriptException:
        try:
            browser.execute_script(
                "document.getElementById('callingButtons-showMoreBtn').click()")
            time.sleep(1)
            browser.execute_script("document.getElementById('roster-button').click()")
        except exceptions.JavascriptException:
            pass

    return count


def hangup():
    global current_meeting
    if current_meeting is None:
        return False

    try:
        hangup_btn = browser.find_element(By.CSS_SELECTOR, SEL_HANGUP)
        hangup_btn.click()
        print(f"Left meeting: {current_meeting.title}")
        discord_notification("Left Meeting", current_meeting.title)
        current_meeting = None
        if hangup_thread:
            hangup_thread.cancel()
        return True
    except exceptions.NoSuchElementException:
        return False


def handle_leave_threshold(current_members, total):
    print(f"Current members: {current_members} / Peak: {total}")
    leave_num  = config.get("leave_threshold_number")
    leave_pct  = config.get("leave_threshold_percentage")

    if leave_num and int(leave_num) > 0:
        if (total - current_members) >= int(leave_num):
            print("Leave threshold (absolute) triggered")
            discord_notification("Left meeting, threshold triggered", current_meeting.title)
            hangup()
            return True

    if leave_pct and 0 < int(leave_pct) <= 100:
        if (current_members / total) * 100 < int(leave_pct):
            print("Leave threshold (percentage) triggered")
            discord_notification("Left meeting, threshold triggered", current_meeting.title)
            hangup()
            return True

    if 0 < current_members < 3:
        print("Last person in meeting")
        discord_notification("Left meeting, last member", current_meeting.title)
        hangup()
        return True

    return False


# ── Schedule countdown & auto-join ────────────────────────────────────────────

# Channel meeting banner aria-label (Vietnamese) looks like:
#   "Cuộc họp đã lên lịch. <TÊN>. Thứ Hai, 9 tháng 2, 2026 12:30. Nhấn enter…"
# The schedule datetime is the "<day> tháng <month>, <year> <H>:<MM>" part. The
# regex anchors on "tháng" + a trailing H:MM so it never matches a date that may
# be embedded in the title (e.g. "Ngày 03.02.2026" / "Lúc 07h15").
_BANNER_DT_RE = re.compile(r'(\d{1,2})\s+tháng\s+(\d{1,2}),\s*(\d{4})\s+(\d{1,2}):(\d{2})')


def _parse_banner_time(aria):
    """Return a datetime for a scheduled-meeting banner aria-label, or None."""
    m = _BANNER_DT_RE.search(aria or "")
    if not m:
        return None
    day, month, year, hour, minute = (int(x) for x in m.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _fmt_td(td):
    """Format a timedelta as HH:MM:SS (or 'N ngày HH:MM:SS')."""
    total = max(int(td.total_seconds()), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days} ngày {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def discover_scheduled_meetings():
    """Scan every (non-blacklisted) channel of every team and parse the start
    time of any scheduled-meeting banner found. Returns a de-duplicated list of
    dicts: {start, title, team_id, channel_id}."""
    found = {}
    teams = get_all_teams()
    for team in teams:
        switch_to_teams_tab()
        card = wait_until_found(
            f"[data-tid='{team.t_id}-team-card']", 5, print_error=False)
        if card is None:
            continue
        try:
            browser.execute_script("arguments[0].click()", card)
        except Exception:
            continue
        time.sleep(2)

        team.channels = _get_channels_from_sidebar(team)
        team.check_blacklist()

        for ch in team.channels:
            if ch.blacklisted:
                continue
            ch_btn = wait_until_found(
                f"[data-tid='channel-list-item-text-{ch.c_id}']", 3, print_error=False)
            if ch_btn is None:
                continue
            try:
                browser.execute_script("arguments[0].click()", ch_btn)
                time.sleep(1.5)
            except Exception:
                continue

            for banner in browser.find_elements(By.CSS_SELECTOR, SEL_MEETING_BANNER):
                try:
                    aria = banner.get_attribute("aria-label") or ""
                except Exception:
                    continue
                start = _parse_banner_time(aria)
                if start is None:
                    continue
                key = (ch.c_id, start.isoformat())
                found[key] = {
                    "start": start,
                    "title": f"{team.name} → {ch.name}",
                    "team_id": team.t_id,
                    "channel_id": ch.c_id,
                }

    switch_to_teams_tab()
    return list(found.values())


# Outlook-calendar event aria-labels (Vietnamese) look like:
#   "môn toán, 5:02 CH đến 5:32 CH, Thứ Hai, Tháng 6 01, 2026, Busy"
# Note the calendar differs from the channel banner: the time is 12-hour with
# SA (AM) / CH (PM), and the date is "Tháng <month> <day>, <year>" (month first).
_CAL_TIME_RE = re.compile(r'(\d{1,2}):(\d{2})\s*(SA|CH)')
_CAL_DATE_RE = re.compile(r'Tháng\s+(\d{1,2})\s+(\d{1,2}),\s*(\d{4})')

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


def _parse_calendar_time(aria):
    """Return the start datetime of an Outlook-calendar event aria-label, or None."""
    tm = _CAL_TIME_RE.search(aria or "")
    dm = _CAL_DATE_RE.search(aria or "")
    if not tm or not dm:
        return None
    hour, minute, ampm = int(tm.group(1)), int(tm.group(2)), tm.group(3)
    if ampm == "CH" and hour != 12:      # PM
        hour += 12
    elif ampm == "SA" and hour == 12:    # 12 AM = midnight
        hour = 0
    month, day, year = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _discover_calendar_events():
    """Read class times the user put on the Outlook calendar. Returns
    [{start, title, source:'calendar'}] (no channel — these are time markers;
    the actual class is joined via its channel)."""
    out = []
    switch_to_calendar_tab()
    time.sleep(3)
    iframe = wait_until_found(SEL_CAL_IFRAME, 15, print_error=False)
    if iframe is None:
        return out

    browser.switch_to.frame(iframe)
    labels = []
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                n = browser.execute_script(
                    'return document.querySelectorAll(\'button,[role="button"]\').length;') or 0
                labels = browser.execute_script(_CAL_EVENTS_JS) or []
            except Exception:
                n, labels = 0, []
            if n > 30 and labels:
                break
            time.sleep(1.5)
    finally:
        browser.switch_to.default_content()

    for al in labels:
        low = al.lower()
        if any(s in low for s in _CAL_SKIP):
            continue
        start = _parse_calendar_time(al)
        if start is None:
            continue
        title = al.split(",")[0].strip()
        # Skip time-block / "working hours" / selection markers: those have no
        # real title (their first segment is itself a time, e.g. "6:00 CH đến …").
        if not title or _CAL_TIME_RE.match(title):
            continue
        out.append({"start": start, "title": title, "source": "calendar"})
    return out


def _join_live_channel_meeting():
    """At class time, scan the channels for a meeting that is open right now and
    join it. Used for calendar-sourced class times (which carry no channel)."""
    global meetings
    meetings = []
    teams = get_all_teams()
    if teams:
        get_meetings(teams)
    to_join = decide_meeting()
    if to_join is not None:
        join_meeting(to_join)
    return current_meeting is not None


def _countdown_until(meeting, join_at, max_seconds):
    """Print a live one-line countdown to join_at. Returns True when join_at is
    reached, or False once max_seconds elapse (caller should then re-scan)."""
    end = time.time() + max_seconds
    while time.time() < end:
        now = datetime.now()
        if now >= join_at:
            sys.stdout.write("\n")
            return True
        remain = join_at - now
        line = (f"\r⏳ {meeting['title']} | bắt đầu {meeting['start']:%H:%M %d/%m}"
                f" | còn {_fmt_td(remain)} | tự vào lúc {join_at:%H:%M}      ")
        sys.stdout.write(line)
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\n")
    return False


def _stay_until_meeting_ends():
    """Block while in a meeting; return when the call ends. Honors the optional
    'leave_if_last' / leave-threshold settings while in the call."""
    global current_meeting, total_members
    interval = max(int(config.get('check_interval', 10) or 10), 3)
    total_members = 0
    count = 0
    while current_meeting is not None:
        if wait_until_found(SEL_HANGUP, 5, print_error=False) is None:
            print("Đã rời lớp / lớp đã kết thúc.")
            current_meeting = None
            return
        if config.get('leave_if_last'):
            members = get_meeting_members()
            if current_meeting is None:
                return
            if members and members > total_members:
                total_members = members
            if count % 5 == 0 and count > 0 and members is not None:
                if handle_leave_threshold(members, total_members):
                    return
        count += 1
        time.sleep(interval)


def run_schedule_loop():
    """Main loop for channel-based classes: discover scheduled meetings, show a
    countdown to the next one, then auto-join it `join_before_min` minutes early
    (retrying until the meeting is actually open)."""
    global current_meeting

    join_before = max(int(config.get('join_before_min', 2) or 0), 0)
    rescan_seconds = max(int(config.get('rescan_min', 10) or 10), 1) * 60
    print(f"Chế độ đếm ngược: tự vào lớp sớm {join_before} phút trước giờ bắt đầu.")

    # Sessions already attended (or attempted) this run, so we don't keep
    # re-joining the class we just left. Keyed by (channel_id, start time).
    handled = set()

    def _key(m):
        return (m.get("channel_id") or m.get("title"), m["start"].isoformat())

    while True:
        print("\nĐang dò lịch học… chờ chút")
        schedule = []
        if mode != 3:   # mode 1 (cả hai) / 2 (chỉ kênh) → quét banner trong kênh
            try:
                schedule += discover_scheduled_meetings()
            except Exception as e:
                print(f"Lỗi khi dò kênh: {e}")
        if mode != 2:   # mode 1 (cả hai) / 3 (chỉ lịch) → đọc sự kiện trên Lịch Outlook
            try:
                schedule += _discover_calendar_events()
            except Exception as e:
                print(f"Lỗi khi đọc lịch: {e}")

        # Khử trùng theo giờ bắt đầu; ưu tiên mục có kênh (vào lớp chính xác hơn).
        by_start = {}
        for m in schedule:
            k = m["start"].isoformat()
            if k not in by_start or (m.get("channel_id") and not by_start[k].get("channel_id")):
                by_start[k] = m
        schedule = list(by_start.values())

        now = datetime.now()
        # Keep upcoming meetings, plus ones that started within the last 3h (a
        # class may still be ongoing). Channels also keep past sessions — ignore
        # those, and ignore any session we have already handled this run.
        upcoming = sorted(
            (m for m in schedule
             if m["start"] >= now - timedelta(hours=3) and _key(m) not in handled),
            key=lambda m: m["start"])

        if not upcoming:
            mins = rescan_seconds // 60
            print(f"Chưa thấy buổi học sắp tới. Quét lại sau {mins} phút.")
            time.sleep(rescan_seconds)
            continue

        nxt = upcoming[0]
        join_at = nxt["start"] - timedelta(minutes=join_before)
        print(f"Buổi kế tiếp: {nxt['title']} — bắt đầu {nxt['start']:%H:%M %d/%m}")

        # Count down (re-scanning periodically in case the schedule changes).
        if not _countdown_until(nxt, join_at, rescan_seconds):
            continue  # window elapsed without reaching join time → re-scan

        # ── Time to join ───────────────────────────────────────────────────
        handled.add(_key(nxt))  # don't re-pick this session after we leave it
        print(f"\n⏰ Tới giờ vào lớp: {nxt['title']}")
        discord_notification("Tới giờ vào lớp", nxt["title"])

        # Retry until joined or 15 min past the scheduled start (the teacher may
        # open the meeting a little late). A channel-sourced item knows its exact
        # channel; a calendar-sourced item only knows the time, so we scan the
        # channels for whatever class is open right now.
        deadline = nxt["start"] + timedelta(minutes=15)
        while datetime.now() < deadline and current_meeting is None:
            if nxt.get("channel_id"):
                # Channel-sourced: navigate to that channel and click its Join.
                join_meeting(Meeting(
                    m_id=f"channel:{nxt['channel_id']}",
                    time_started=int(time.time()),
                    title=nxt["title"],
                    calendar_meeting=False,
                    channel_id=nxt["channel_id"],
                    team_id=nxt["team_id"],
                ))
            else:
                # Calendar-sourced: open the meeting ON THE CALENDAR and click
                # "Tham gia" (the user's classes are Teams meetings on the calendar).
                join_meeting(Meeting(
                    m_id=f"calendar:{nxt['title']}@{nxt['start'].isoformat()}",
                    time_started=int(time.time()),
                    title=nxt["title"],
                    calendar_meeting=True,
                ))
            if current_meeting is not None:
                break
            print("Lớp chưa mở để vào — thử lại sau 20 giây…")
            time.sleep(20)

        if current_meeting is None:
            print("Không vào được lớp (quá giờ). Tìm buổi tiếp theo.")
            continue

        _stay_until_meeting_ends()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global config, meetings, mode, total_members, current_meeting

    mode = config.get("meeting_mode", 1)
    if not (0 < mode < 4):
        mode = 1

    email    = config.get('email', '')
    password = config.get('password', '')

    if not email:
        email = input('Email: ')
    if not password:
        password = getpass('Password: ')

    init_browser()
    browser.get("https://teams.microsoft.com")

    # Login
    if email and password:
        login_email = wait_until_found("input[type='email']", 30)
        if login_email:
            login_email.send_keys(email)
        login_email = wait_until_found("input[type='email']", 5)
        if login_email:
            login_email.send_keys(Keys.ENTER)

        login_pwd = wait_until_found("input[type='password']", 10)
        if login_pwd:
            login_pwd.send_keys(password)
        login_pwd = wait_until_found("input[type='password']", 5)
        if login_pwd:
            login_pwd.send_keys(Keys.ENTER)

        keep_logged_in = wait_until_found("input[id='idBtn_Back']", 5)
        if keep_logged_in:
            keep_logged_in.click()
            discord_notification("Logged in successfully", " ")
        else:
            print("Login may have failed — check config.json credentials")
            discord_notification("Login may have failed", "check config.json")

        use_web = wait_until_found(".use-app-lnk", 5, print_error=False)
        if use_web:
            use_web.click()

    if config.get('organisation_num', -1) >= 0:
        change_organisation(config['organisation_num'])

    print("Waiting for Teams to load…", end='')
    for _ in range(3):
        if wait_until_found(SEL_PAGE_READY, 60) is not None:
            break
        retry = wait_until_found("button.oops-button", 10)
        if retry:
            retry.click()
        else:
            exit(1)
    print("\rTeams loaded. Do not click anything in the browser from now on.")

    time.sleep(5)

    # Every mode uses the countdown loop: it reads each class's start time (from
    # the channel banner and/or the Outlook calendar depending on the mode),
    # shows a live countdown, and auto-joins `join_before_min` minutes early.
    #   mode 1 = both sources · mode 2 = channels only · mode 3 = calendar only.
    run_schedule_loop()


if __name__ == "__main__":
    # By default, open the web setup form. Pass --no-gui to skip it and use
    # config.json directly (useful for scheduled / headless runs).
    use_gui = "--no-gui" not in sys.argv

    if use_gui:
        import setup_ui
        config = setup_ui.run_setup_gui()
    else:
        try:
            load_config()
        except Exception as e:
            print("Configuration file missing or in wrong format")
            print(str(e))
            exit(1)

    if config.get('run_at_time'):
        now = datetime.now()
        run_at = datetime.strptime(config['run_at_time'], "%H:%M").replace(
            year=now.year, month=now.month, day=now.day)
        if run_at.time() < now.time():
            run_at = run_at.replace(day=now.day + 1)
        delay = (run_at - now).total_seconds()
        print(f"Waiting until {run_at} ({int(delay)}s)")
        time.sleep(delay)

    try:
        main()
    finally:
        if browser:
            browser.quit()
        if hangup_thread:
            hangup_thread.cancel()
        discord_notification("Browser closed", "Thank you!")
