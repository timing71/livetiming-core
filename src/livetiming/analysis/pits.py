from livetiming.analysis import Analysis
from livetiming.racing import Stat, FlagStatus
import math

# Credit this many extra laps for every lap of yellow in a stint
YELLOW_LAP_MODIFIER = 0.5


class Car(object):
    def __init__(self, car):
        self.num = car
        self.stints = []
        self.inPit = True
        self.laps = 0
        self.stintFlags = []

    def pitIn(self, lap, timestamp):
        if len(self.stints) > 0:
            currentStint = self.stints[-1]
            currentStint.append(lap)
            currentStint.append(timestamp)
            currentStint.append(False)
            currentStint.append(self.activeStintYellows())
        self.inPit = True

    def pitOut(self, lap, timestamp, flag):
        if self.inPit:
            self.stints.append([lap, timestamp])
            self.inPit = False
            self.stintFlags = [flag]

    def predictedStop(self):
        if len(self.stints) > 1:  # If we've made at least one stop
            if len(self.stints[-1]) == 2:  # We're currently on track
                stintsToConsider = map(lambda stint: (stint[2] - stint[0]) + (YELLOW_LAP_MODIFIER * stint[5]), self.stints[0:-1])
                outLap = self.stints[-1][0]
                return math.floor(float(sum(stintsToConsider) / len(stintsToConsider)) - (self.laps - outLap) + (YELLOW_LAP_MODIFIER * self.activeStintYellows()))
        return None

    def activeStintYellows(self):
        return len([f for f in self.stintFlags if f >= FlagStatus.YELLOW])


class PitStopAnalysis(Analysis):

    def __init__(self):
        self.cars = {}
        self.lapReckoner = {}
        self.latestTimestamp = 0
        self.currentFlag = FlagStatus.NONE

    def getName(self):
        return "Pit stops"

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):
        numIdx = colSpec.index(Stat.NUM)
        lapCountIdx = colSpec.index(Stat.LAPS) if Stat.LAPS in colSpec else None
        stateIdx = colSpec.index(Stat.STATE)
        lastLapIdx = colSpec.index(Stat.LAST_LAP)

        self.currentFlag = FlagStatus.fromString(newState["session"].get("flagState", "none"))

        self.latestTimestamp = timestamp
        for newCar in newState["cars"]:
            num = newCar[numIdx]
            lap = int(newCar[lapCountIdx]) if lapCountIdx else self.lapReckoner[num] if num in self.lapReckoner else 0
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:

                oldCarState = oldCar[stateIdx]
                newCarState = newCar[stateIdx]

                self._getCar(num).stintFlags[-1] = max(self.currentFlag, self._getCar(num).stintFlags[-1])

                try:
                    if oldCar[lastLapIdx][0] != newCar[lastLapIdx][0]:
                        self.lapReckoner[num] = lap + 1
                        self._getCar(num).stintFlags.append(self.currentFlag)
                except:
                    if oldCar[lastLapIdx] != newCar[lastLapIdx]:
                        self.lapReckoner[num] = lap + 1
                        self._getCar(num).stintFlags.append(self.currentFlag)
                self._getCar(num).laps = self.lapReckoner.get(num, 0)

                if newCarState == "PIT" and oldCarState != "PIT":
                    self._getCar(num).pitIn(lap, timestamp)
                elif newCarState != "PIT" and oldCarState == "PIT":
                    self._getCar(num).pitOut(lap, timestamp, self.currentFlag)

            else:
                self._getCar(num).pitOut(lap, timestamp, self.currentFlag)

    def _getCar(self, car):
        if car not in self.cars:
            self.cars[car] = Car(car)
        return self.cars[car]

    def getData(self):
        '''
        Data format:
        {
          "cars": {
            "carNum": [
              [
                [outLap, outTime, inLap, inTime, inProgress, lapsUnderYellow]
              ],
              inPit,
              lap,
              predictedStopLap
            ]
          }
        },
        "latestTimestamp": latestTimestamp
        '''
        mappedData = {"cars": {}, "latestTimestamp": self.latestTimestamp}

        for num, car in self.cars.iteritems():
            mappedStints = []
            for stint in car.stints:
                if len(stint) == 6:
                    mappedStints.append(stint)
                else:
                    mappedStints.append(stint + [None, self.latestTimestamp, True, car.activeStintYellows()])
            mappedData["cars"][num] = [mappedStints, car.inPit, car.laps, car.predictedStop()]

        return mappedData
