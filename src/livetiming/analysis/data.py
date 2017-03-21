from livetiming.racing import Stat, FlagStatus
from livetiming.recording import RecordingFile
import copy
import math
import re
import sys
import time

# Credit this many extra laps for every lap of yellow in a stint
YELLOW_LAP_MODIFIER = 0.5

TSNL_LAP_HACK_REGEX = re.compile("-- ([0-9]+) laps?")


class Car(object):
    def __init__(self, race_num):
        self.race_num = race_num
        self.laps = []
        self._stints = []
        self.inPit = True
        self.current_lap = 0
        self._current_lap_flags = [FlagStatus.NONE]
        self._current_stint_flags = []

    def add_lap(self, laptime, current_flag=FlagStatus.NONE):
        max_flag = max(self._current_lap_flags)
        self.laps.append([
            self.current_lap,
            laptime,
            max_flag
        ])
        self._current_stint_flags.append(max_flag)
        self._current_lap_flags = [current_flag]

    def see_flag(self, flag):
        self._current_lap_flags.append(flag)

    def pitIn(self, timestamp):
        if len(self._stints) > 0:
            currentStint = self._stints[-1]
            currentStint.append(self.current_lap)
            currentStint.append(timestamp)
            currentStint.append(False)
            currentStint.append(self.activeStintYellows)
        self.inPit = True

    def pitOut(self, timestamp, flag):
        if self.inPit:
            self._stints.append([self.current_lap, timestamp])
            self.inPit = False
            self._current_stint_flags = [flag]

    def predictedStop(self):
        if len(self._stints) > 1:  # If we've made at least one stop
            if len(self._stints[-1]) == 2:  # We're currently on track
                stintsToConsider = map(lambda stint: (stint[2] - stint[0]) + (YELLOW_LAP_MODIFIER * stint[5]), self._stints[0:-1])
                outLap = self._stints[-1][0]
                return math.floor(float(sum(stintsToConsider) / len(stintsToConsider)) - (self.current_lap - outLap) + (YELLOW_LAP_MODIFIER * self.activeStintYellows))
        return None

    @property
    def activeStintYellows(self):
        return len([f for f in self._current_stint_flags if f >= FlagStatus.YELLOW])

    @property
    def stints(self):
        stints = []
        for stint in self._stints:
            if len(stint) == 6:
                stints.append(stint)
            else:
                stints.append(stint + [None, None, True, self.activeStintYellows])
        return stints


class Session(object):
    def __init__(self):
        self._flag_periods = []
        self.this_period = None

    def flag_change(self, newFlag, leaderLap, timestamp):
        if self.this_period:
            self._flag_periods.append(self.this_period + [leaderLap, timestamp])
        self.this_period = [newFlag, leaderLap, timestamp]

    @property
    def flag_periods(self):
        return self._flag_periods + [self.this_period + [None, None]]


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.colSpec = colSpec

    def get(self, car, field):
        if field in self.colSpec:
            idx = self.colSpec.index(field)
            return car[idx]
        return None


class DataCentre(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.cars = {}
        self.session = Session()
        self.oldState = {"cars": [], "session": {"flagState": "none"}, "messages": []}
        self.leaderLap = 0

    def car(self, race_num):
        if race_num not in self.cars:
            self.cars[race_num] = Car(race_num)
        return self.cars[race_num]

    def update_state(self, newState, colSpec, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        if newState["session"].get("flagState", "none") != "none":
            self._update_cars(self.oldState, newState, colSpec, timestamp)
            self._update_session(self.oldState, newState, colSpec, timestamp)
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
                self.leaderLap = max(self.leaderLap, car.current_lap)

                if old_flag != flag:
                    car.see_flag(flag)
                new_car_state = f.get(new_car, Stat.STATE)

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

                    old_car_state = f.get(old_car, Stat.STATE)

                    if new_car_state == "PIT" and old_car_state != "PIT":
                        car.pitIn(timestamp)
                    elif new_car_state != "PIT" and old_car_state == "PIT":
                        car.pitOut(timestamp, flag)
                elif new_car_state != "PIT":
                    car.pitOut(timestamp, flag)

    def _update_session(self, oldState, newState, colSpec, timestamp):
        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))
        old_flag = FlagStatus.fromString(oldState["session"].get("flagState", "none"))
        if flag != old_flag:
            self.session.flag_change(flag, self.leaderLap, timestamp)

    def _get_lap_count(self, race_num, car, f, cars):
        from_timing = f.get(car, Stat.LAPS)
        if from_timing:
            return from_timing
        else:
            our_num = f.get(car, Stat.NUM)
            # TSNL put lap count in the "gap" column FSR
            tsnl = TSNL_LAP_HACK_REGEX.match(f.get(cars[0], Stat.GAP))
            if tsnl:
                # Work up until we find the lap count relevant to us
                lap_count = int(tsnl.group(1))
                for other_car in cars:
                    tsnl = TSNL_LAP_HACK_REGEX.match(f.get(other_car, Stat.GAP))
                    if tsnl:
                        lap_count = int(tsnl.group(1))
                    if f.get(other_car, Stat.NUM) == our_num:
                        return lap_count
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
