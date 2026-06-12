"""Shared mutable bot state. Other modules do `import runtime as rt`."""

browser = None            # selenium webdriver, set by browser.init_browser()
config = {}               # merged config dict, set by main
meetings = []
current_meeting = None
already_joined_ids = []
handled = set()           # class sessions already joined/attempted this run
channel_to_team = {}      # {channel_thread_id: team_thread_id}
hangup_thread = None      # threading.Timer for auto-leave
mode = 3
total_members = None
