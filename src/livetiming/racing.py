from enum import Enum


class FlagStatus(Enum):
    GREEN = 0
    YELLOW = 1
    FCY = 2
    CODE_60 = 3
    SC = 4
    RED = 5
    CHEQUERED = 6
    WHITE = 7
    VSC = 8
    NONE = 999

    @classmethod
    def fromString(fs, string):
        return FlagStatus[string.upper()]


class Stat(Enum):
    NUM = ("Num", "text")
    STATE = ("State", "text")
    CLASS = ("Class", "class")
    TEAM = ("Team", "text")
    DRIVER = ("Driver", "text")
    CAR = ("Car", "text")
    TYRE = ("T", "text")
    TYRE_STINT = ("TS", "text", "Tyre stint - laps on these tyres since last stop")
    TYRE_AGE = ("TA", "text", "Tyre age - total laps on these tyres from new")
    LAPS = ("Laps", "numeric")
    GAP = ("Gap", "delta", "Gap to leader")
    INT = ("Int", "delta", "Interval to car in front")
    LAST_LAP = ("Last", "time")
    BEST_LAP = ("Best", "time")
    S1 = ("S1", "time", "Sector 1 time")
    S2 = ("S2", "time", "Sector 2 time")
    S3 = ("S3", "time", "Sector 3 time")
    SPEED = ("Spd", "numeric")
    PITS = ("Pits", "numeric")

    def __init__(self, title, ttype, description=None):
        self.title = title
        self.type = ttype
        self.description = description
