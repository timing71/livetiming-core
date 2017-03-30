from livetiming.analysis import Analysis


class LapChart(Analysis):

    def getName(self):
        return "Lap chart"

    def getData(self):
        times = map(
            lambda car: map(
                lambda l: (l.lap_num, l.laptime, l.flag.name.lower()),
                car.laps
            ),
            self.data_centre.cars
        )

        return {
            "numLaps": self.data_centre.leader_lap,
            "laps": {l: f.name.lower() for l, f in self.data_centre.session.lap_flags.iteritems()},
            "times": times
        }
