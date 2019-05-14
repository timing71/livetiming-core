from enum import Enum


class Channels(Enum):
    SEASONS = '_SEASONS_JSON'
    SEASON = '_SEASON_JSON'
    SCHEDULE = '_SCHEDULE_{meeting_id}_JSON'
    TIMING = '_TIMING_{session_id}_JSON'
    COMP_DETAIL = '_COMP_DETAIL_{session_id}_JSON'

    def formatted_value(self, **kwargs):
        return self.value.format(**kwargs)


class CompetitionStatus(Enum):
    SCHEDULED = 2
    RUNNING = 4
    UNOFFICIAL = 6
    OFFICIAL = 7
    OFFICIAL_8 = 8
    COMING_UP = 50
    OFFICIAL_999 = 999


class ResultStatus(Enum):
    START_LIST = 1
    RUNNING = 2
    INTERMEDIATE = 3
    PARTIAL = 4
    UNCONFIRMED = 5
    UNOFFICIAL = 6
    OFFICIAL = 7
    PROTESTED = 8
    UNKNOWN = 99
