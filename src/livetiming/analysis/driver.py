from livetiming.analysis import Analysis
from livetiming.racing import Stat


class StintLength(Analysis):
    def __init__(self):
        self.stints = {}

    def getName(self):
        return "Driver stints"

    def getData(self):
        '''
        Data format is:
          {
            "carNum": {
              "driver1": [
                [startLap, endLap]
              ],
              "driver2": [
                [startLap]
              ]
            }
          }
        '''
        return self.stints

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):
        numIdx = colSpec.index(Stat.NUM)
        lapCountIdx = colSpec.index(Stat.LAPS)
        driverIdx = colSpec.index(Stat.DRIVER)

        for newCar in newState["cars"]:
            num = newCar[numIdx]
            newDriver = newCar[driverIdx]
            lapCount = newCar[lapCountIdx]
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:
                oldDriver = oldCar[driverIdx]
                if oldDriver != newDriver:
                    self._endDriverStint(num, oldDriver, lapCount, timestamp)
                    self._startDriverStint(num, newDriver, lapCount, timestamp)
            else:
                self._startDriverStint(num, newDriver, lapCount, timestamp)

    def _startDriverStint(self, car, driver, lapCount, timestamp):
        if car not in self.stints:
            self.stints[car] = {}
        if driver not in self.stints[car]:
            self.stints[car][driver] = []
        self.stints[car][driver].append([lapCount, timestamp])

    def _endDriverStint(self, car, driver, lapCount, timestamp):
        if car in self.stints:
            if driver in self.stints[car]:
                if len(self.stints[car][driver]) > 0:
                    self.stints[car][driver][-1] += [lapCount, timestamp]
