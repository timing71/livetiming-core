from livetiming.analysis import Analysis


class LaptimeAnalysis(Analysis):

    def getName(self):
        return "Lap times"

    def getData(self):
        times = {}

        for car in self.data_centre.cars.values():
            times[car.race_num] = {
                "name": next(iter(car.drivers)),
                "laptimes": map(lambda l: (l.lap_num, l.laptime, l.flag.name.lower()), car.laps)
            }

        return {
            "numLaps": self.data_centre.leader_lap,
            "laps": {l: f.name.lower() for l, f in self.data_centre.session.lap_flags.iteritems()},
            "times": times
        }
