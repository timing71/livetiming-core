from livetiming.analysis import Analysis


def _lap_chart_add_entry(chart, pos, lap, race_num):
    if pos not in chart:
        chart[pos] = {}
    if lap not in chart[pos]:
        chart[pos][lap] = race_num


class LapChart(Analysis):
    def getName(self):
        return "Lap chart"

    def getData(self):
        lap_chart = {}

        for car in self.data_centre.cars:
            for lap in car.laps:
                _lap_chart_add_entry(lap_chart, lap.position, lap.lap_num, car.race_num)

        return lap_chart
