"""Shared mutable bot state. Other modules do `import runtime as rt`."""

browser = None            # selenium webdriver, set by browser.init_browser()
config = {}               # merged config dict, set by main
current_meeting = None
handled = set()           # class sessions already joined/attempted this run
channel_to_team = {}      # {channel_thread_id: team_thread_id}
hangup_thread = None      # threading.Timer for auto-leave
mode = 3
total_members = None
schedule = []             # last scan result, sorted by start (indexes the UI uses)
join_request = None       # class the user clicked "join now" on, resolved at click time
joining = False           # a join attempt is in flight (current_meeting is not set yet)
