from livetiming.analysis import Analysis


def _lap_chart_add_entry(chart, race_num, lap):
    pos = lap.position
    lap_num = lap.lap_num
    if pos not in chart:
        chart[pos] = {}
    if lap_num not in chart[pos]:
        chart[pos][lap_num] = [race_num] + lap.for_json()


class LapChart(Analysis):
    def getName(self):
        return "Lap chart"

    def getData(self):
        lap_chart = {}

        for car in self.data_centre.cars:
            for lap in car.laps:
                _lap_chart_add_entry(lap_chart, car.race_num, lap)

        return lap_chart
