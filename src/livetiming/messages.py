import re
import time

from racing import FlagStatus
from livetiming.racing import Stat


def formatTime(seconds):
    # print "formatTime called with {}".format(seconds)
    m, s = divmod(seconds, 60)
    return "{}:{:0>6.3f}".format(int(m), s)


class TimingMessage(object):
    def _consider(self, oldState, newState):
        pass

    def process(self, oldState, newState):
        msg = self._consider(oldState, newState)
        if msg:
            return [[int(time.time())] + msg]
        return []


class PerCarMessage(TimingMessage):
    def __init__(self, columnSpec=None):
        self.columnSpec = columnSpec

    def getValue(self, car, stat, default=None):
        if self.columnSpec and stat in self.columnSpec:
            idx = self.columnSpec.index(stat)
            if idx < len(car):
                return car[idx]
        return default

    def process(self, oldState, newState):
        messages = []
        if Stat.NUM in self.columnSpec:
            for newCar in newState["cars"]:
                oldCars = [c for c in oldState["cars"] if c[0] == newCar[0] and c[0] is not None and c[0] != ""]
                if oldCars:
                    oldCar = oldCars[0]
                    msg = self._consider(oldCar, newCar)
                    if msg:
                        messages += [[int(time.time())] + msg + [newCar[0]]]
        return messages


# Emits a message if the flag status of the state has changed.
class FlagChangeMessage(TimingMessage):

    def _consider(self, oldState, newState):
        def getFlag(s):
            if "session" in s and "flagState" in s["session"]:
                return FlagStatus.fromString(s["session"]["flagState"])
            return FlagStatus.NONE

        oldFlag = getFlag(oldState)
        newFlag = getFlag(newState)

        if oldFlag != newFlag:
            if newFlag == FlagStatus.GREEN:
                return ["Track", "Green flag - track clear", "green"]
            elif newFlag == FlagStatus.SC:
                return ["Track", "Safety car deployed", "yellow"]
            elif newFlag == FlagStatus.FCY:
                return ["Track", "Full course yellow", "yellow"]
            elif newFlag == FlagStatus.YELLOW:
                return ["Track", "Yellow flags shown", "yellow"]
            elif newFlag == FlagStatus.RED:
                return ["Track", "Red flag", "red"]
            elif newFlag == FlagStatus.CHEQUERED:
                return ["Track", "Chequered flag", "track"]
            elif newFlag == FlagStatus.CODE_60:
                return ["Track", "Code 60", "code60"]
            elif newFlag == FlagStatus.VSC:
                return ["Track", "Virtual safety car deployed", "yellow"]
            elif newFlag == FlagStatus.CAUTION:
                return ["Track", "Full course caution", "yellow"]


# Emits a message if a car enters or leaves the pits, or retires.
class CarPitMessage(PerCarMessage):

    def _consider(self, oldCar, newCar):
        oldStatus = self.getValue(oldCar, Stat.STATE)
        newStatus = self.getValue(newCar, Stat.STATE)

        carNum = self.getValue(newCar, Stat.NUM)
        driver = self.getValue(newCar, Stat.DRIVER)
        clazz = self.getValue(newCar, Stat.CLASS, "Pits")

        if oldStatus != newStatus and carNum is not None:
            if (oldStatus != 'RUN' and newStatus == "OUT") or (newStatus == "RUN" and oldStatus == "PIT"):
                return [clazz, u"#{} ({}) has left the pits".format(carNum, driver), "out"]
            elif newStatus == "PIT":
                return [clazz, u"#{} ({}) has entered the pits".format(carNum, driver), "pit"]
            elif newStatus == "FUEL":
                return [clazz, u"#{} ({}) has entered the fuelling area".format(carNum, driver), "pit"]
            elif newStatus == "RET":
                return [clazz, u"#{} ({}) has retired".format(carNum, driver), ""]
            elif newStatus == 'STOP':
                return [clazz, u"#{} ({}) is running slowly or stopped".format(carNum, driver), ""]
            elif oldStatus == 'STOP' and newStatus == 'RUN':
                return [clazz, u"#{} ({}) has resumed".format(carNum, driver), ""]


# Emits a message if the driver of a car changes.
class DriverChangeMessage(PerCarMessage):

    def _consider(self, oldCar, newCar):
        oldDriver = self.getValue(oldCar, Stat.DRIVER)
        newDriver = self.getValue(newCar, Stat.DRIVER)
        carNum = self.getValue(newCar, Stat.NUM)
        if oldDriver != newDriver and carNum is not None:
            if oldDriver == "":
                return [self.getValue(newCar, Stat.CLASS, "Pits"), u"#{} Driver change (to {})".format(carNum, newDriver)]
            elif newDriver != "":
                return [self.getValue(newCar, Stat.CLASS, "Pits"), u"#{} Driver change ({} to {})".format(carNum, oldDriver, newDriver)]


# Emits a message if a car sets a personal or overall best.
class FastLapMessage(PerCarMessage):

    def _consider(self, oldCar, newCar):
        carNum = self.getValue(newCar, Stat.NUM)
        driver = self.getValue(newCar, Stat.DRIVER)
        clazz = self.getValue(newCar, Stat.CLASS, "Timing")
        oldTime = self.getValue(oldCar, Stat.LAST_LAP)
        newTime = self.getValue(newCar, Stat.LAST_LAP)
        if oldTime and newTime and carNum and len(oldTime) > 1 and len(newTime) > 1:
            oldFlags = oldTime[1]
            newFlags = newTime[1]

            if (newTime[0] or 0) > 0 and (oldFlags != newFlags or oldTime[0] != newTime[0]):
                if newFlags == "pb" and (oldFlags == "" or newTime[0] < oldTime[0]):
                    return [clazz, u"#{} ({}) set a new personal best: {}".format(carNum, driver, formatTime(newTime[0])), "pb"]
                elif newFlags == "sb-new":
                    return [clazz, u"#{} ({}) set a new overall best: {}".format(carNum, driver, formatTime(newTime[0])), "sb"]


CAR_NUMBER_REGEX = re.compile("car #? ?(?P<race_num>[0-9]+)", re.IGNORECASE)


class RaceControlMessage(TimingMessage):

    def __init__(self, messageList):
        self.messageList = messageList

    def process(self, oldState, newState):
        msgs = []
        while len(self.messageList) > 0:
            nextMessage = self.messageList.pop()
            hasCarNum = self.CAR_NUMBER_REGEX.search(nextMessage)
            if hasCarNum:
                msgs.append([int(time.time()), "Race Control", nextMessage.upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([int(time.time()), "Race Control", nextMessage.upper(), "raceControl"])
        return msgs
