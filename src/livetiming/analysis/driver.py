from livetiming.analysis import Analysis


class StintLength(Analysis):

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
        for car in self.data_centre.cars:
            mappedStints[car.race_num] = self._mapStints(car)
        return mappedStints

    def _mapStints(self, car):
        mappedStints = []

        all_stints = iter(car.stints)
        stint = next(all_stints, None)

        while stint:

            start_stint = stint

            while stint and stint.driver == start_stint.driver:
                end_stint = stint
                stint = next(all_stints, None)

            laps_in_stint = [l for l in car.laps if l.lap_num >= start_stint.start_lap and (l.lap_num <= end_stint.end_lap or end_stint.end_lap is None)]
            fastest_lap = min(map(lambda l: l.laptime, laps_in_stint)) if len(laps_in_stint) > 0 else None

            if end_stint.in_progress:
                mappedStints.append([
                    start_stint.driver,
                    start_stint.start_lap,
                    start_stint.start_time,
                    car.current_lap,
                    self.data_centre.latest_timestamp,
                    1,
                    fastest_lap
                ])
            else:
                mappedStints.append([
                    start_stint.driver,
                    start_stint.start_lap,
                    start_stint.start_time,
                    end_stint.end_lap,
                    end_stint.end_time,
                    0,
                    fastest_lap
                ])
        return mappedStints
