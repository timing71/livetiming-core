from livetiming.analysis import Analysis
from livetiming.racing import Stat


class StintLength(Analysis):
    def __init__(self):
        self.reset()

    def reset(self):
        self.stints = {}
        self.carPitInTimes = {}
        self.carPitOutTimes = {}
        self.carLaps = {}
        self.latestTimestamp = 0

        self.lapReckoner = {}
        self.prevLaptimes = {}

        self.fastestLaps = {}

    def getName(self):
        return "Driver stints"

    def getData(self):
        '''
        Data format is:
          {
            "carNum": [
              ["driver1",startLap, startTime, endLap, endTime, 0, bestLap]
              ["driver2", startLap, startTime, currentLap, currentTime, 1, bestLap]
            ]
          }
        '''
        mappedStints = {}
        for car, stints in self.stints.iteritems():
            mappedStints[car] = self._mapStints(car, stints)
        return mappedStints

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):
        numIdx = colSpec.index(Stat.NUM)
        lapCountIdx = colSpec.index(Stat.LAPS) if Stat.LAPS in colSpec else None
        driverIdx = colSpec.index(Stat.DRIVER)
        stateIdx = colSpec.index(Stat.STATE)
        lastLapIdx = colSpec.index(Stat.LAST_LAP)

        self.latestTimestamp = timestamp

        for newCar in newState["cars"]:
            num = newCar[numIdx]
            newDriver = newCar[driverIdx]
            if lapCountIdx:
                lapCount = int(newCar[lapCountIdx]) if newCar[lapCountIdx] != "" else 0
            else:
                lapCount = self.lapReckoner[num] if num in self.lapReckoner else 0
            self.carLaps[num] = lapCount
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:

                oldCarState = oldCar[stateIdx]
                newCarState = newCar[stateIdx]
                oldDriver = oldCar[driverIdx]

                try:
                    if oldCar[lastLapIdx][0] != newCar[lastLapIdx][0]:
                        self.prevLaptimes[num] = newCar[lastLapIdx][0]
                        self.lapReckoner[num] = lapCount + 1
                        self.fastestLaps[num] = min(self.fastestLaps.get(num, 9999999), newCar[lastLapIdx][0])
                except:
                    if oldCar[lastLapIdx] != newCar[lastLapIdx]:
                        self.prevLaptimes[num] = newCar[lastLapIdx]
                        self.lapReckoner[num] = lapCount + 1
                        self.fastestLaps[num] = min(self.fastestLaps.get(num, 9999999), newCar[lastLapIdx])

                if newCarState == "PIT" and oldCarState != "PIT":
                    self.carPitInTimes[num] = timestamp
                elif newCarState != "PIT" and oldCarState == "PIT":
                    self.carPitOutTimes[num] = timestamp

                if oldDriver != newDriver:
                    if num in self.carPitInTimes:
                        self._endDriverStint(num, lapCount, self.carPitInTimes.pop(num))
                    else:
                        self._endDriverStint(num, lapCount, timestamp)

                    if num in self.carPitOutTimes:
                        self._startDriverStint(num, newDriver, lapCount, self.carPitOutTimes.pop(num))
                    else:
                        self._startDriverStint(num, newDriver, lapCount, timestamp)
            else:
                self._startDriverStint(num, newDriver, lapCount, timestamp)
                self.prevLaptimes[num] = newCar[lastLapIdx]

    def _startDriverStint(self, car, driver, lapCount, timestamp):
        if car not in self.stints:
            self.stints[car] = []
        if car in self.fastestLaps:
            self.fastestLaps.pop(car)
        self.stints[car].append([driver, lapCount, timestamp])

    def _endDriverStint(self, car, lapCount, timestamp):
        if car in self.stints:
            if len(self.stints[car]) > 0:
                fastLap = self.fastestLaps.get(car, None)
                self.stints[car][-1] += [lapCount, timestamp, 0, fastLap]

    def _mapStints(self, car, stints):
        mappedStints = []
        for stint in stints:
            if len(stint) == 7:
                mappedStints.append(stint)
            else:
                fastLap = self.fastestLaps.get(car, None)
                mappedStints.append(stint + [self.carLaps[car], self.latestTimestamp, 1, fastLap])
        return mappedStints
