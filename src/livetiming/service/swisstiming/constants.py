from enum import Enum


class Channels(Enum):
    SEASONS = '_SEASONS_JSON'


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
