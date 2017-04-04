from livetiming.analysis import Analysis


def _lap_chart_add_entry(chart, race_num, lap, is_in_lap):
    pos = lap.position
    lap_num = lap.lap_num
    if pos not in chart:
        chart[pos] = {}
    if lap_num not in chart[pos]:
        chart[pos][lap_num] = [race_num] + lap.for_json() + [is_in_lap]


class LapChart(Analysis):
    def getName(self):
        return "Lap chart"

    def getData(self):
        lap_chart = {}

        for car in self.data_centre.cars:
            in_laps = map(lambda s: s.end_lap, car.stints)
            for lap in car.laps:
                _lap_chart_add_entry(lap_chart, car.race_num, lap, lap.lap_num in in_laps)

        return lap_chart
