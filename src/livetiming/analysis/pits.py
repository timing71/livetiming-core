from livetiming.analysis import Analysis
import math

# Credit this many extra laps for every lap of yellow in a stint
YELLOW_LAP_MODIFIER = 0.5


def predict_endurance_stop(car):
    if len(car.stints) > 1:  # If we've made at least one stop
        if car.current_stint.in_progress:  # We're currently on track
            stintsToConsider = map(lambda stint: (stint.end_lap - stint.start_lap) + (YELLOW_LAP_MODIFIER * stint.yellow_laps), car.stints[0:-1])
            outLap = car.stints[-1].start_lap
            return math.floor(float(sum(stintsToConsider) / len(stintsToConsider)) - (car.current_lap - outLap) + (YELLOW_LAP_MODIFIER * car.current_stint.yellow_laps))
    return None


class EnduranceStopAnalysis(Analysis):

    def getName(self):
        return "Pit stops"

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
        cars = {}

        for race_num, car in self.data_centre.cars.iteritems():
            mappedStints = []
            for stint in car.stints:
                if stint.in_progress:
                    mappedStints.append([
                        stint.start_lap,
                        stint.start_time,
                        None,
                        self.data_centre.latest_timestamp,
                        True,
                        stint.yellow_laps
                    ])
                else:
                    mappedStints.append([
                        stint.start_lap,
                        stint.start_time,
                        stint.end_lap,
                        stint.end_time,
                        False,
                        stint.yellow_laps
                    ])

            cars[race_num] = [mappedStints, car.inPit, car.current_lap, predict_endurance_stop(car)]

        return {"cars": cars, "latestTimestamp": self.data_centre.latest_timestamp}
