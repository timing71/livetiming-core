from livetiming.analysis import Analysis
from livetiming.racing import Stat, FlagStatus


class LaptimeAnalysis(Analysis):
    def __init__(self):
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
        lapCountIdx = colSpec.index(Stat.LAPS)
        driverIdx = colSpec.index(Stat.DRIVER)

        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))

        if len(newState["cars"]) > 0:
            leader = newState["cars"][0]
            lapNum = int(leader[lapCountIdx])
            self.laps[lapNum] = max(self.laps.get(lapNum, -1), flag)

        for newCar in newState["cars"]:
            num = newCar[numIdx]
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

        for num, laptimes in self.laptimes.iteritems():
            times[num] = {
                "name": self.drivers.get(num, "-"),
                "laptimes": map(lambda l: (l[0], l[1], l[2].name.lower()), laptimes)
            }

        return {
            "numLaps": len(self.laps.keys()),
            "laps": {l: f.name.lower() for l, f in self.laps.iteritems()},
            "times": times
        }
