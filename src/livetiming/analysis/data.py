from livetiming.racing import Stat, FlagStatus
from livetiming.recording import RecordingFile
import copy
import re
import sys
import time


class Car(object):
    def __init__(self, race_num):
        self.race_num = race_num
        self.laps = []
        self.current_lap = 0
        self._current_lap_flags = [FlagStatus.NONE]

    def add_lap(self, laptime, current_flag=FlagStatus.NONE):
        self.laps.append([
            self.current_lap,
            laptime,
            max(self._current_lap_flags)
        ])
        self._current_lap_flags = [current_flag]

    def see_flag(self, flag):
        self._current_lap_flags.append(flag)


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.colSpec = colSpec

    def get(self, car, field):
        idx = self.colSpec.index(field)
        if idx is not None:
            return car[idx]
        return None


class DataCentre(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.cars = {}
        self.oldState = {"cars": [], "session": {"flagState": "none"}, "messages": []}

    def car(self, race_num):
        if race_num not in self.cars:
            self.cars[race_num] = Car(race_num)
        return self.cars[race_num]

    def update_state(self, newState, colSpec, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        if newState["session"].get("flagState", "none") != "none":
            self._update_cars(self.oldState, newState, colSpec, timestamp)
            self.oldState = copy.deepcopy(newState)

    def _update_cars(self, oldState, newState, colSpec, timestamp):
        f = FieldExtractor(colSpec)
        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))
        old_flag = FlagStatus.fromString(oldState["session"].get("flagState", "none"))

        for new_car in newState['cars']:
            race_num = f.get(new_car, Stat.NUM)
            if race_num:
                car = self.car(race_num)
                car.current_lap = self._get_lap_count(race_num, new_car, f, newState['cars'])

                if old_flag != flag:
                    car.see_flag(flag)

                old_car = next(iter([c for c in oldState["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)

                if old_car:

                    old_lap = f.get(old_car, Stat.LAST_LAP)
                    new_lap = f.get(new_car, Stat.LAST_LAP)
                    old_lap_num = f.get(old_car, Stat.LAPS)
                    new_lap_num = f.get(new_car, Stat.LAPS)

                    try:
                        if old_lap[0] != new_lap[0] or old_lap_num != new_lap_num:
                            car.add_lap(new_lap[0], flag)
                    except:  # Non-tuple case (do any services still not use tuples?)
                        if old_lap != new_lap or old_lap_num != new_lap_num:
                            car.add_lap(new_lap, flag)

    def _get_lap_count(self, race_num, car, f, cars):
        from_timing = f.get(car, Stat.LAPS)
        if from_timing:
            return from_timing
        elif re.match("-- [0-9]+ laps?", f.get(cars[0], Stat.GAP)):
            # TSNL workaround
            pass
        else:
            return len(self.car(race_num).laps)


if __name__ == '__main__':
    recFile = sys.argv[1]
    dc = DataCentre()
    rec = RecordingFile(recFile)

    colSpec = Stat.parse_colspec(rec.manifest['colSpec'])

    for i in range(rec.frames + 1):
        newState = rec.getStateAt(i * int(rec.manifest['pollInterval']))
        dc.update_state(newState, colSpec, rec.manifest['startTime'] + (i * int(rec.manifest['pollInterval'])))
        print "{}/{}".format(i, rec.frames)
