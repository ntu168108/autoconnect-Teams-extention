"""Chrome/Edge lifecycle, login, and wait helpers."""

import time

from selenium import webdriver
from selenium.common import exceptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import runtime as rt
import selectors_teams as S
import status
from notify import discord_notification


def init_browser():
    if rt.config.get('chrome_type') == "msedge":
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

    if rt.config.get('headless'):
        chrome_options.add_argument('--headless=new')
        status.log("Enabled headless mode")

    if rt.config.get('mute_audio'):
        chrome_options.add_argument("--mute-audio")

    # Selenium 4.6+ bundles Selenium Manager — no explicit driver path needed.
    if rt.config.get('chrome_type') == "msedge":
        rt.browser = webdriver.Edge(options=chrome_options)
    else:
        if rt.config.get('chrome_type') == "chromium" and rt.config.get("chromium_binary"):
            chrome_options.binary_location = rt.config["chromium_binary"]
        rt.browser = webdriver.Chrome(options=chrome_options)

    w = rt.browser.get_window_size()
    if w['width'] < 1200:
        rt.browser.set_window_size(1200, w['height'])
    if w['height'] < 850:
        rt.browser.set_window_size(w['width'], 850)


def wait_until_found(sel, timeout, print_error=True):
    try:
        WebDriverWait(rt.browser, timeout).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
        return rt.browser.find_element(By.CSS_SELECTOR, sel)
    except exceptions.TimeoutException:
        if print_error:
            status.log(f"Timeout waiting for element: {sel}")
            discord_notification("Timeout error", sel)
        return None


def wait_present(sel, timeout):
    """Like wait_until_found but only requires the element to exist in the DOM,
    not to be visible. Needed for Fluent UI toggle inputs (the real <input> is
    visually hidden with opacity:0, so a visibility check never matches)."""
    try:
        WebDriverWait(rt.browser, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
        return rt.browser.find_element(By.CSS_SELECTOR, sel)
    except exceptions.TimeoutException:
        return None


def switch_to_teams_tab():
    btn = wait_until_found(S.SEL_TEAMS_BTN, 5, print_error=False)
    if btn:
        rt.browser.execute_script("arguments[0].click()", btn)
        time.sleep(1)


def switch_to_calendar_tab():
    btn = wait_until_found(S.SEL_CALENDAR_BTN, 5, print_error=False)
    if btn:
        rt.browser.execute_script("arguments[0].click()", btn)
        time.sleep(1)


def change_organisation(org_num):
    # New Teams profile button id: idna-me-control-avatar-trigger
    profile_button = wait_until_found("button#idna-me-control-avatar-trigger", 20)
    if profile_button is None:
        profile_button = wait_until_found("button#personDropdown", 10)
    if profile_button is None:
        status.log("Could not find profile button while changing organisation")
        return

    profile_button.click()

    change_org_button = wait_until_found(
        f"li[aria-posinset='{org_num + 1}']", 10)
    if change_org_button is None:
        status.log("Could not find organisation button")
        return

    try:
        change_org_button.find_element(By.CSS_SELECTOR, "button.active")
    except exceptions.NoSuchElementException:
        pass
    else:
        status.log("Organisation not changed (already selected)")
        return

    change_org_button.click()
    time.sleep(5)


def browser_dead(e):
    """True if the exception means the Chrome session is gone (window closed,
    crashed, or DevTools disconnected) — i.e. we must reopen the browser."""
    if isinstance(e, (exceptions.InvalidSessionIdException,
                      exceptions.NoSuchWindowException)):
        return True
    if isinstance(e, exceptions.WebDriverException):
        msg = (getattr(e, "msg", None) or str(e) or "").lower()
        return any(k in msg for k in (
            "invalid session id", "no such window", "disconnected",
            "not connected to devtools", "target window already closed",
            "chrome not reachable", "browser has closed", "session deleted"))
    return False


def open_and_login(email, password):
    """Open Chrome, go to Teams, log in with the given credentials, and wait
    until the Teams app is ready. Reused for the first launch and for restarts."""
    status.report("starting", detail="Đang mở Chrome và đăng nhập…")
    init_browser()
    rt.browser.get("https://teams.microsoft.com")

    if email and password:
        e = wait_until_found("input[type='email']", 30)
        if e:
            e.send_keys(email)
        e = wait_until_found("input[type='email']", 5)
        if e:
            e.send_keys(Keys.ENTER)

        p = wait_until_found("input[type='password']", 10)
        if p:
            p.send_keys(password)
        p = wait_until_found("input[type='password']", 5)
        if p:
            p.send_keys(Keys.ENTER)

        keep = wait_until_found("input[id='idBtn_Back']", 5)
        if keep:
            keep.click()
            discord_notification("Logged in successfully", " ")
        else:
            status.log("Login may have failed — check config.json credentials")
            discord_notification("Login may have failed", "check config.json")

        use_web = wait_until_found(".use-app-lnk", 5, print_error=False)
        if use_web:
            use_web.click()

    if rt.config.get('organisation_num', -1) >= 0:
        change_organisation(rt.config['organisation_num'])

    status.log("Đang chờ Teams tải xong…")
    for _ in range(3):
        if wait_until_found(S.SEL_PAGE_READY, 60) is not None:
            break
        retry = wait_until_found("button.oops-button", 10)
        if retry:
            retry.click()
        else:
            break
    status.log("Teams đã tải xong. Đừng bấm gì vào cửa sổ Chrome.")
    time.sleep(5)
