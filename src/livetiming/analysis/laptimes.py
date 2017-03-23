from livetiming.analysis import Analysis


class LapChart(Analysis):

    def getName(self):
        return "Lap chart"

    def getData(self):
        times = {}

        for car in self.data_centre.cars.values():
            try:
                driver_name = next(iter(car.drivers))
            except StopIteration:
                driver_name = ""
            times[car.race_num] = {
                "name": driver_name,
                "laptimes": map(lambda l: (l.lap_num, l.laptime, l.flag.name.lower()), car.laps)
            }

        return {
            "numLaps": self.data_centre.leader_lap,
            "laps": {l: f.name.lower() for l, f in self.data_centre.session.lap_flags.iteritems()},
            "times": times
        }
