from racing import FlagStatus
import time


def formatTime(seconds):
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
    def process(self, oldState, newState):
        messages = []
        for newCar in newState["cars"]:
            oldCars = [c for c in oldState["cars"] if c[0] == newCar[0]]
            if oldCars:
                oldCar = oldCars[0]
                msg = self._consider(oldCar, newCar)
                if msg:
                    messages += [[int(time.time())] + msg + [newCar[0]]]
        return messages


# Emits a message if the flag status of the state has changed.
class FlagChangeMessage(TimingMessage):
    def __init__(self, getFlag):
        self.getFlag = getFlag

    def _consider(self, oldState, newState):
        oldFlag = self.getFlag(oldState)
        newFlag = self.getFlag(newState)
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


# Emits a message if a car enters or leaves the pits, or retires.
class CarPitMessage(PerCarMessage):
    def __init__(self, getPitStatus, getClass, getDriver):
        self.getPitStatus = getPitStatus
        self.getClass = getClass
        self.getDriver = getDriver

    def _consider(self, oldCar, newCar):
        oldStatus = self.getPitStatus(oldCar)
        newStatus = self.getPitStatus(newCar)
        if oldStatus != newStatus:
            if newStatus == "OUT" or (newStatus == "RUN" and oldStatus == "PIT"):
                return [self.getClass(newCar), u"#{} ({}) has left the pits".format(newCar[0], self.getDriver(newCar)), "out"]
            elif newStatus == "PIT":
                return [self.getClass(newCar), u"#{} ({}) has entered the pits".format(newCar[0], self.getDriver(newCar)), "pit"]
            elif newStatus == "RET":
                return [self.getClass(newCar), u"#{} ({}) has retired".format(newCar[0], self.getDriver(newCar)), ""]


# Emits a message if the driver of a car changes.
class DriverChangeMessage(PerCarMessage):
    def __init__(self, getClass, getDriver):
        self.getClass = getClass
        self.getDriver = getDriver

    def _consider(self, oldCar, newCar):
        oldDriver = self.getDriver(oldCar)
        newDriver = self.getDriver(newCar)
        if oldDriver != newDriver:
            return [self.getClass(newCar), u"#{} Driver change ({} to {})".format(newCar[0], oldDriver, newDriver)]


# Emits a message if a car sets a personal or overall best.
class FastLapMessage(PerCarMessage):
    def __init__(self, getTime, getClass, getDriver):
        self.getTime = getTime
        self.getClass = getClass
        self.getDriver = getDriver

    def _consider(self, oldCar, newCar):
        oldTime = self.getTime(oldCar)
        newTime = self.getTime(newCar)
        oldFlags = oldTime[1]
        newFlags = newTime[1]
        if newTime[0] > 0 and (oldFlags != newFlags or oldTime[0] != newTime[0]):
            if newFlags == "pb":
                return [self.getClass(newCar), u"#{} ({}) set a new personal best: {}".format(newCar[0], self.getDriver(newCar), formatTime(newTime[0])), "pb"]
            elif newFlags == "sb-new":
                return [self.getClass(newCar), u"#{} ({}) set a new overall best: {}".format(newCar[0], self.getDriver(newCar), formatTime(newTime[0])), "sb"]
