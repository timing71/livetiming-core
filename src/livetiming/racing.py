from enum import Enum, IntEnum


class FlagStatus(IntEnum):
    NONE = 0
    GREEN = 1
    WHITE = 2
    CHEQUERED = 3
    YELLOW = 4
    FCY = 5
    CODE_60 = 6
    VSC = 7
    SC = 8
    CAUTION = 9
    RED = 10
    SLOW_ZONE = 11
    CODE_60_ZONE = 12

    @staticmethod
    def fromString(string):
        return FlagStatus[string.upper()]


class Stat(Enum):
    NUM = ("Num", "text", "Car number")
    STATE = ("State", "text")
    CLASS = ("Class", "class")
    TEAM = ("Team", "text")
    DRIVER = ("Driver", "text")
    CAR = ("Car", "text")
    TYRE = ("T", "text", "Tyre")
    TYRE_STINT = ("TS", "text", "Tyre stint - laps on these tyres since last stop")
    TYRE_AGE = ("TA", "text", "Tyre age - total laps on these tyres from new")
    LAPS = ("Laps", "numeric")
    GAP = ("Gap", "delta", "Gap to leader")
    CLASS_GAP = ("C.Gap", "delta", "Gap to class leader")
    INT = ("Int", "delta", "Interval to car in front")
    CLASS_INT = ("C.Int", "delta", "Interval to class car in front")
    LAST_LAP = ("Last", "time", "Last lap time")
    BEST_LAP = ("Best", "time", "Best lap time")
    S1 = ("S1", "time", "Sector 1 time")
    S2 = ("S2", "time", "Sector 2 time")
    S3 = ("S3", "time", "Sector 3 time")
    S4 = ("S4", "time", "Sector 4 time")
    S5 = ("S5", "time", "Sector 5 time")
    BS1 = ("BS1", "time", "Best sector 1 time")
    BS2 = ("BS2", "time", "Best sector 2 time")
    BS3 = ("BS3", "time", "Best sector 3 time")
    BS4 = ("BS4", "time", "Best sector 4 time")
    BS5 = ("BS5", "time", "Best sector 5 time")
    SPEED = ("Spd", "numeric", "Last lap speed")
    BEST_SPEED = ("B.Spd", "numeric", "Best lap speed")
    PITS = ("Pits", "numeric")
    PUSH_TO_PASS = ("PTP", "numeric", "Push-to-Pass remaining")
    DRIVER_1_BEST_LAP = ("D1 Best", "time", "Driver 1 best lap")
    DRIVER_2_BEST_LAP = ("D2 Best", "time", "Driver 2 best lap")
    AGGREGATE_BEST_LAP = ("Average", "time", "Average of best laps")
    POS_IN_CLASS = ("PIC", "numeric", "Position in class")
    T1_SPEED = ("T1 Spd", "numeric", "Turn 1 speed")
    BEST_T1_SPEED = ("BT1S", "numeric", "Best turn 1 speed")
    T3_SPEED = ("T3 Spd", "numeric", "Turn 3 speed")
    BEST_T3_SPEED = ("BT3S", "numeric", "Best turn 3 speed")
    NO_TOW_SPEED = ('NTS', 'numeric', 'No-tow speed - best speed without tow')
    NO_TOW_RANK = ('NTR', 'numeric', 'No-tow rank')

    def __init__(self, title, ttype, description=None):
        self.title = title
        self.type = ttype
        self.description = description

    @staticmethod
    def from_title(title):
        if title == "Lap":
            return Stat.LAPS  # Hack hack hack :(
        for s in Stat:
            if s.title == title:
                return s
        return None

    @staticmethod
    def parse_colspec(colSpec):
        return [Stat.from_title(s[0]) for s in colSpec]

    @staticmethod
    def sector(key):
        return (
            "S{}".format(key),
            'time',
            "Sector {} time".format(key)
        )

    @staticmethod
    def best_sector(key):
        return (
            "BS{}".format(key),
            'time',
            "Best sector {} time".format(key)
        )
