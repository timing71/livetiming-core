from racing import FlagStatus
import time


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
        print "Comparing {} to {}".format(oldFlag, newFlag)
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