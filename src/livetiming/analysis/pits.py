from livetiming.analysis import Analysis
from livetiming.racing import Stat


class Car(object):
    def __init__(self, car):
        self.num = car
        self.stints = []
        self.inPit = False
        self.laps = 0

    def pitIn(self, lap, timestamp):
        if len(self.stints) > 0:
            currentStint = self.stints[-1]
            currentStint.append(lap)
            currentStint.append(timestamp)
            currentStint.append(False)
        self.inPit = True

    def pitOut(self, lap, timestamp):
        self.stints.append([lap, timestamp])
        self.inPit = False

    def predictedStop(self):
        if len(self.stints) > 1:  # If we've made at least one stop
            if len(self.stints[-1]) == 2:  # We're currently on track
                stintsToConsider = map(lambda stint: stint[2] - stint[0], self.stints[0:-1])
                outLap = self.stints[-1][0]
                return float(sum(stintsToConsider) / len(stintsToConsider)) - (self.laps - outLap)
        return None


class PitStopAnalysis(Analysis):

    def __init__(self):
        self.cars = {}
        self.lapReckoner = {}
        self.latestTimestamp = 0

    def getName(self):
        return "Pit stops"

    def receiveStateUpdate(self, oldState, newState, colSpec, timestamp):
        numIdx = colSpec.index(Stat.NUM)
        lapCountIdx = colSpec.index(Stat.LAPS) if Stat.LAPS in colSpec else None
        stateIdx = colSpec.index(Stat.STATE)
        lastLapIdx = colSpec.index(Stat.LAST_LAP)

        self.latestTimestamp = timestamp
        for newCar in newState["cars"]:
            num = newCar[numIdx]
            lap = int(newCar[lapCountIdx]) if lapCountIdx else self.lapReckoner[num] if num in self.lapReckoner else 0
            oldCar = next(iter([c for c in oldState["cars"] if c[numIdx] == num] or []), None)
            if oldCar:

                oldCarState = oldCar[stateIdx]
                newCarState = newCar[stateIdx]

                try:
                    if oldCar[lastLapIdx][0] != newCar[lastLapIdx][0]:
                        self.lapReckoner[num] = lap + 1
                except:
                    if oldCar[lastLapIdx] != newCar[lastLapIdx]:
                        self.lapReckoner[num] = lap + 1
                self._getCar(num).laps = self.lapReckoner.get(num, 0)

                if newCarState == "PIT" and oldCarState != "PIT":
                    self._getCar(num).pitIn(lap, timestamp)
                elif newCarState != "PIT" and oldCarState == "PIT":
                    self._getCar(num).pitOut(lap, timestamp)

            else:
                self._getCar(num).pitOut(lap, timestamp)

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
                [outLap, outTime, inLap, inTime, inProgress]
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
                if len(stint) == 5:
                    mappedStints.append(stint)
                else:
                    mappedStints.append(stint + [None, self.latestTimestamp, True])
            mappedData["cars"][num] = [mappedStints, car.inPit, car.laps, car.predictedStop()]

        return mappedData
