from livetiming.analysis import Analysis
from livetiming.racing import Stat, FlagStatus


class LaptimeAnalysis(Analysis):
    def __init__(self):
        self.reset()

    def reset(self):
        self.laptimes = {}
        self.thisLapFlags = {}

        self.laps = {}
        self.drivers = {}

    def _addLaptime(self, carNum, laptime):
        if carNum not in self.laptimes:
            self.laptimes[carNum] = []
        self.laptimes[carNum].append(laptime)

    def getName(self):
        return "Lap times"

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):

        numIdx = colSpec.index(Stat.NUM)
        lapIdx = colSpec.index(Stat.LAST_LAP)
        lapCountIdx = colSpec.index(Stat.LAPS) if Stat.LAPS in colSpec else None
        driverIdx = colSpec.index(Stat.DRIVER)

        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))

        if len(newState["cars"]) > 0:
            if lapCountIdx:
                lapNum = max(map(lambda c: int(c[lapCountIdx]) if c[lapCountIdx] != "" else 0, newState["cars"]))  # as in practice the "leader" might not have done as many laps as others
            else:
                leader = newState["cars"][0]
                lapNum = len(self.laptimes[leader[numIdx]]) - 1 if leader[numIdx] in self.laptimes else 0
            self.laps[lapNum] = max(self.laps.get(lapNum, -1), flag)

        for newCar in newState["cars"]:
            num = newCar[numIdx]
            if lapCountIdx:
                lapNum = int(newCar[lapCountIdx]) if newCar[lapCountIdx] != "" else 0
            else:
                lapNum = len(self.laptimes[num]) if num in self.laptimes else 0
            self.drivers[num] = newCar[driverIdx]
            self.thisLapFlags[num] = max(flag, self.thisLapFlags.get(num, FlagStatus.NONE))
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:
                oldLap = oldCar[lapIdx]
                newLap = newCar[lapIdx]
                try:
                    if oldLap[0] != newLap[0]:
                        self._addLaptime(num, (lapNum, newLap[0], self.thisLapFlags.get(num, "none")))
                        self.thisLapFlags[num] = flag
                except:  # Non-tuple case (do any services still not use tuples?)
                    if oldLap != newLap:
                        self._addLaptime(num, (lapNum, newLap, self.thisLapFlags.get(num, "none")))
                        self.thisLapFlags[num] = flag

    def getData(self):
        times = {}

        for num, driver in self.drivers.iteritems():
            times[num] = {"name": driver}

        for num, laptimes in self.laptimes.iteritems():
            if num not in times:
                times[num] = {"name": "-"}
            times[num]["laptimes"] = map(lambda l: (l[0], l[1], l[2].name.lower()), laptimes)

        return {
            "numLaps": max(self.laps.keys()),
            "laps": {l: f.name.lower() for l, f in self.laps.iteritems()},
            "times": times
        }
