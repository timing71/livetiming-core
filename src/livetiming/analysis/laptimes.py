from livetiming.analysis import Analysis
from livetiming.racing import Stat, FlagStatus


class LaptimeAnalysis(Analysis):
    def __init__(self):
        self.laptimes = {}
        self.lapFlags = {}

    def _addLaptime(self, carNum, laptime):
        if carNum not in self.laptimes:
            self.laptimes[carNum] = []
        self.laptimes[carNum].append(laptime)

    def getName(self):
        return "Lap times"

    def receiveStateUpdate(self, oldState, newState, colSpec):

        numIdx = colSpec.index(Stat.NUM)
        lapIdx = colSpec.index(Stat.LAST_LAP)
        lapCountIdx = colSpec.index(Stat.LAPS)

        flag = newState["session"].get("flagState", "none")

        for newCar in newState["cars"]:
            num = newCar[numIdx]
            self.lapFlags[num] = max(flag, self.lapFlags.get(num, FlagStatus.NONE))
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:
                oldLap = oldCar[lapIdx]
                newLap = newCar[lapIdx]
                try:
                    if oldLap[0] != newLap[0]:
                        self._addLaptime(num, (int(newCar[lapCountIdx]), newLap[0], self.lapFlags.get(num, "none")))
                        self.lapFlags[num] = flag
                except:  # Non-tuple case (do any services still not use tuples?)
                    if oldLap != newLap:
                        self._addLaptime(num, (int(newCar[lapCountIdx]), newLap, self.lapFlags.get(num, "none")))
                        self.lapFlags[num] = flag

    def getData(self):
        return self.laptimes
