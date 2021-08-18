import re
import time

from .racing import FlagStatus
from livetiming.racing import Stat
from twisted.logger import Logger


def formatTime(seconds):
    # print "formatTime called with {}".format(seconds)
    m, s = divmod(seconds, 60)
    return "{}:{:0>6.3f}".format(int(m), s)


class TimingMessage(object):
    log = Logger()

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
                wanted_num = self.getValue(newCar, Stat.NUM)
                wanted_car = self.getValue(newCar, Stat.CAR)
                wanted_clazz = self.getValue(newCar, Stat.CLASS)
                oldCars = [
                    c for c in oldState["cars"] if self.getValue(c, Stat.NUM) == wanted_num
                    and self.getValue(c, Stat.CAR) == wanted_car
                    and self.getValue(c, Stat.CLASS) == wanted_clazz
                ]
                oldCar = None

                if len(oldCars) == 1:
                    oldCar = oldCars[0]
                elif len(oldCars) > 0:
                    self.log.warn('Found {count} cars with race number {num} that are indistinguishable!', count=len(oldCars), num=newCar[0])

                if oldCar:
                    msg = self._consider(oldCar, newCar)
                    if msg:
                        messages += [[int(time.time())] + msg + [newCar[0]]]
        return messages


def getFlag(s):
    if "session" in s and "flagState" in s["session"]:
        return FlagStatus.fromString(s["session"]["flagState"])
    return FlagStatus.NONE


class FlagChangeMessage(TimingMessage):
    '''
    Emits a message if the flag status of the state has changed, excluding slow zones.

    Slow zones for VLN/N24 generate more detailed messages than can be created here,
    so slow zone messages are opt-in using the SlowZoneMessage generator.

    '''
    def _consider(self, oldState, newState):
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
            elif newFlag == FlagStatus.WHITE:
                return ["Track", "White flag - final lap", "white"]


class SlowZoneMessage(TimingMessage):
    '''
    Emits a message when slow zone(s) are put into operation.

    Does NOT emit a message when slow zones are lifted - that's covered by the
    normal FlagChangeMessage generator.
    '''
    def _consider(self, oldState, newState):
        oldFlag = getFlag(oldState)
        newFlag = getFlag(newState)

        if oldFlag != FlagStatus.SLOW_ZONE and newFlag == FlagStatus.SLOW_ZONE:
            return ['Track', 'Slow zone(s) in operation', 'yellow']


# Emits a message if a car enters or leaves the pits, or retires.
class CarPitMessage(PerCarMessage):

    def _consider(self, oldCar, newCar):
        oldStatus = self.getValue(oldCar, Stat.STATE)
        newStatus = self.getValue(newCar, Stat.STATE)

        carNum = self.getValue(newCar, Stat.NUM)
        driver = self.getValue(newCar, Stat.DRIVER)
        clazz = self.getValue(newCar, Stat.CLASS, "Pits")

        if driver:
            car_num_and_driver = "#{} ({})".format(carNum, driver)
        else:
            car_num_and_driver = "#{}".format(carNum)

        if oldStatus != newStatus and carNum is not None and oldStatus != 'N/S':
            if (oldStatus != 'RUN' and newStatus == "OUT") or (newStatus == "RUN" and oldStatus == "PIT"):
                return [clazz, "{} has left the pits".format(car_num_and_driver), "out"]
            elif newStatus == "PIT":
                return [clazz, "{} has entered the pits".format(car_num_and_driver), "pit"]
            elif newStatus == "FUEL":
                return [clazz, "{} has entered the fuelling area".format(car_num_and_driver), "pit"]
            elif newStatus == "RET":
                return [clazz, "{} has retired".format(car_num_and_driver), ""]
            elif newStatus == 'STOP':
                return [clazz, "{} is running slowly or stopped".format(car_num_and_driver), ""]
            elif oldStatus == 'STOP' and newStatus == 'RUN':
                return [clazz, "{} has resumed".format(car_num_and_driver), ""]


# Emits a message if the driver of a car changes.
class DriverChangeMessage(PerCarMessage):

    def _consider(self, oldCar, newCar):
        oldDriver = self.getValue(oldCar, Stat.DRIVER)
        newDriver = self.getValue(newCar, Stat.DRIVER)
        carNum = self.getValue(newCar, Stat.NUM)
        if oldDriver != newDriver and carNum is not None:
            if not oldDriver:
                return [self.getValue(newCar, Stat.CLASS, "Pits"), "#{} Driver change (to {})".format(carNum, newDriver), None]
            elif newDriver:
                return [self.getValue(newCar, Stat.CLASS, "Pits"), "#{} Driver change ({} to {})".format(carNum, oldDriver, newDriver), None]
            else:
                return [self.getValue(newCar, Stat.CLASS, "Pits"), "#{} Driver change (from {} to nobody)".format(carNum, oldDriver), None]


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

            if isinstance(oldTime[0], float) and isinstance(newTime[0], float):
                if (newTime[0] or 0) > 0 and (oldFlags != newFlags or oldTime[0] != newTime[0]):
                    if driver:
                        car_num_and_driver = "#{} ({})".format(carNum, driver)
                    else:
                        car_num_and_driver = "#{}".format(carNum)
                    try:
                        if newFlags == "pb" and (oldFlags == "" or newTime[0] < oldTime[0]):
                            return [clazz, "{} set a new personal best: {}".format(car_num_and_driver, formatTime(newTime[0])), "pb"]
                        elif newFlags == "sb-new":
                            return [clazz, "{} set a new overall best: {}".format(car_num_and_driver, formatTime(newTime[0])), "sb"]
                    except TypeError:
                        return None


CAR_NUMBER_REGEX = re.compile("car #? ?(?P<race_num>[0-9]+)", re.IGNORECASE)


class RaceControlMessage(TimingMessage):

    def __init__(self, messageList):
        self.messageList = messageList

    def process(self, oldState, newState):
        msgs = []
        while len(self.messageList) > 0:
            nextMessage = self.messageList.pop()
            hasCarNum = CAR_NUMBER_REGEX.search(nextMessage)
            if hasCarNum:
                msgs.append([int(time.time()), "Race Control", nextMessage.upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([int(time.time()), "Race Control", nextMessage.upper(), "raceControl"])
        return msgs
