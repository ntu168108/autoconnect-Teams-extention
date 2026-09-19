"""Data classes shared by scanner / joiner / schedule."""

import runtime as rt


class Channel:
    def __init__(self, name, c_id, blacklisted=False):
        self.name = name
        self.c_id = c_id
        self.blacklisted = blacklisted


class Team:
    def __init__(self, name, t_id, channels=None):
        self.name = name
        self.t_id = t_id
        self.channels = channels if channels is not None else []

    def check_blacklist(self):
        blacklist = rt.config.get('blacklist', [])
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
    """One class to join. Built by schedule.py from a scanned schedule entry."""

    def __init__(self, m_id, title, calendar_meeting=False,
                 channel_id=None, team_id=None, thread_id=None, reply_id=None):
        self.m_id = m_id
        self.title = title
        self.calendar_meeting = calendar_meeting
        self.channel_id = channel_id
        self.team_id = team_id
        # Teams thread + message id, from the calendar API. Together they form
        # the meeting's own join link (see joiner._open_meeting_by_link).
        self.thread_id = thread_id
        self.reply_id = reply_id
