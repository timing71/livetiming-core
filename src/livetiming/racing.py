from enum import Enum


class FlagStatus(Enum):
    GREEN = 0
    YELLOW = 1
    FCY = 2
    CODE_60 = 3
    SC = 4
    RED = 5
    CHEQUERED = 6,
    WHITE = 7,
    VSC = 8,
    NONE = 999

    @classmethod
    def fromString(fs, string):
        return FlagStatus[string.upper()]
