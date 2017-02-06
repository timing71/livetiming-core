from livetiming.analysis import Analysis
from livetiming.racing import Stat


class StintLength(Analysis):
    def __init__(self):
        self.stints = {}
        self.carPitInTimes = {}
        self.carPitOutTimes = {}
        self.carLaps = {}
        self.latestTimestamp = 0

    def getName(self):
        return "Driver stints"

    def getData(self):
        '''
        Data format is:
          {
            "carNum": [
              ["driver1",startLap, startTime, endLap, endTime]
              ["driver2", startLap, startTime, currentLap, currentTime, 1]
            ]
          }
        '''
        mappedStints = {}
        for car, stints in self.stints.iteritems():
            mappedStints[car] = self._mapStints(car, stints)
        return mappedStints

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):
        numIdx = colSpec.index(Stat.NUM)
        lapCountIdx = colSpec.index(Stat.LAPS)
        driverIdx = colSpec.index(Stat.DRIVER)
        stateIdx = colSpec.index(Stat.STATE)

        self.latestTimestamp = timestamp

        for newCar in newState["cars"]:
            num = newCar[numIdx]
            newDriver = newCar[driverIdx]
            lapCount = newCar[lapCountIdx]
            self.carLaps[num] = lapCount
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:

                oldCarState = oldCar[stateIdx]
                newCarState = newCar[stateIdx]
                oldDriver = oldCar[driverIdx]

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

    def _startDriverStint(self, car, driver, lapCount, timestamp):
        if car not in self.stints:
            self.stints[car] = []
        self.stints[car].append([driver, lapCount, timestamp])

    def _endDriverStint(self, car, lapCount, timestamp):
        if car in self.stints:
            if len(self.stints[car]) > 0:
                self.stints[car][-1] += [lapCount, timestamp]

    def _mapStints(self, car, stints):
        mappedStints = []
        for stint in stints:
            if len(stint) == 5:
                mappedStints.append(stint)
            else:
                mappedStints.append(stint + [self.carLaps[car], self.latestTimestamp, 1])
        return mappedStints
