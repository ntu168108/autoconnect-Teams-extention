"""Data classes shared by scanner / joiner / schedule."""

import re

import runtime as rt


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
        if rt.config.get('blacklist_meeting_re'):
            return bool(re.search(rt.config['blacklist_meeting_re'], self.title))
        return False

    def __str__(self):
        return (f"\t{self.title} {self.time_started}"
                + (" [Calendar]" if self.calendar_meeting else " [Channel]")
                + (" [BLACKLISTED]" if self.calendar_blacklisted else ""))
