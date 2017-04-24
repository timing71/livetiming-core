from collections import defaultdict
from livetiming.analysis import Analysis


class LaptimeChart(Analysis):
    def getName(self):
        return "Lap chart"

    def getData(self):
        lap_chart = defaultdict(dict)

        in_laps = {}
        for car in self.data_centre.cars:
            in_laps[car.race_num] = map(lambda s: s.end_lap, car.stints)

        for lap_num, laps in self.data_centre.lap_chart.iteritems():
            for posMinusOne, (race_num, lap) in enumerate(laps):
                lap_chart[posMinusOne + 1][lap_num] = [race_num] + lap.for_json() + [lap_num in in_laps[race_num]]

        return lap_chart
