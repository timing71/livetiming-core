from collections import defaultdict, OrderedDict
from livetiming.racing import Stat, FlagStatus
from livetiming.recording import RecordingFile
import cPickle
import copy
import re
import sys
import time

TSNL_LAP_HACK_REGEX = re.compile("\(([0-9]+) laps?")


class LaptimeChart(object):
    def __init__(self):
        self.laps = defaultdict(list)
        self._seen_on_lap = defaultdict(list)

    def tally(self, race_num, lap):
        if race_num not in self._seen_on_lap[lap.lap_num]:
            self.laps[lap.lap_num].append((race_num, lap))
            self._seen_on_lap[lap.lap_num].append(race_num)

    def iteritems(self):
        return self.laps.iteritems()


class Lap(object):
    def __init__(self, lap_num, position, laptime, driver, timestamp, flag, tyre):
        self.lap_num = lap_num
        self.laptime = laptime
        self.position = position
        self.driver = driver
        self.timestamp = timestamp
        self.flag = flag
        self.tyre = tyre

    def for_json(self):
        return [
            self.lap_num,
            self.laptime,
            self.position,
            self.driver,
            self.timestamp,
            self.flag,
            self.tyre
        ]

    def __repr__(self, *args, **kwargs):
        return "<Lap {}: {} pos {} {} {} {} {}>".format(*self.for_json())


class Stint(object):
    def __init__(self, start_lap, start_time, driver, flag=FlagStatus.NONE, tyre=None):
        self.start_lap = start_lap
        self.start_time = start_time
        self.driver = driver
        self.end_lap = None
        self.end_time = None
        self.in_progress = True
        self.laps = []
        self.tyre = tyre

    def finish(self, end_lap, end_time):
        self.end_lap = end_lap
        self.end_time = end_time
        self.in_progress = False

    @property
    def yellow_laps(self):
        return len([l for l in self.laps if l.flag >= FlagStatus.YELLOW])

    def __repr__(self, *args, **kwargs):
        return "<Stint: {} laps {}-{} time {}-{} yellows {} in progress? {} >".format(
            self.driver,
            self.start_lap,
            self.end_lap,
            self.start_time,
            self.end_time,
            self.yellow_laps,
            self.in_progress
        )


class Car(object):
    def __init__(self, race_num):
        self.race_num = race_num
        self.laps = []
        self.stints = []
        self.inPit = True
        self.current_lap = 0
        self._current_lap_flags = [FlagStatus.NONE]
        self.initial_driver = None
        self.fuel_times = []

    def add_lap(self, laptime, position, driver, timestamp, current_flag=FlagStatus.NONE, tyre=None):
        max_flag = max(self._current_lap_flags)

        if not self.current_stint:
            self.stints.append(Stint(self.current_lap, timestamp, driver, current_flag))

        if laptime > 0:
            # Some services e.g. F1 don't give a laptime for the first lap.
            # We still want to consider flags for the stint though.
            self.laps.append(
                Lap(
                    self.current_lap,
                    position,
                    laptime,
                    driver,
                    timestamp,
                    max_flag,
                    tyre
                )
            )

        self.current_stint.laps.append(self.laps[-1])
        self._current_lap_flags = [current_flag]

    def see_flag(self, flag):
        self._current_lap_flags.append(flag)

    def set_driver(self, driver):
        if self.current_stint:
            self.current_stint.driver = driver
        else:
            self.initial_driver = driver

    def pit_in(self, timestamp):
        if len(self.stints) > 0:
            currentStint = self.stints[-1]
            currentStint.finish(self.current_lap, timestamp)
        self.inPit = True

    def pit_out(self, timestamp, driver, flag):
        if self.inPit:
            self.stints.append(Stint(self.current_lap, timestamp, driver, flag))
            self.inPit = False

    def fuel_start(self, timestamp):
        self.fuel_times.append([timestamp, None])

    def fuel_stop(self, timestamp):
        if self.fuel_times:
            self.fuel_times[-1][1] = timestamp

    @property
    def current_stint(self):
        if len(self.stints) > 0:
            return self.stints[-1]
        return None

    @property
    def drivers(self):
        if not self.current_stint:
            return [self.initial_driver]
        return set(map(lambda stint: stint.driver, self.stints))

    def driver_name(self):
        try:
            return next(iter(self.drivers))
        except StopIteration:
            return ""


class Session(object):
    def __init__(self):
        self._flag_periods = []
        self.lap_flags = {}
        self.this_period = None

    def flag_change(self, newFlag, leaderLap, timestamp):
        self.lap_flags[leaderLap] = max(self.lap_flags.get(leaderLap, FlagStatus.NONE), newFlag)
        if self.this_period and self.this_period[0] != newFlag:
            self._flag_periods.append(self.this_period + [leaderLap, timestamp])
        if not self.this_period or self.this_period[0] != newFlag:
            self.this_period = [newFlag, leaderLap, timestamp]

    @property
    def flag_periods(self):
        if self.this_period:
            return self._flag_periods + [self.this_period + [None, None]]
        return self._flag_periods


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.mapping = {}
        for idx, col in enumerate(colSpec):
            self.mapping[col] = idx

    def get(self, car, field, default=None):
        try:
            return car[self.mapping[field]]
        except KeyError:
            return default


def tryInt(val):
    try:
        return int(val)
    except Exception:
        return val


class DataCentre(object):
    def __init__(self):
        self.reset()
        self.latest_timestamp = None

    def reset(self):
        self._cars = OrderedDict()
        self.session = Session()
        self.current_state = {"cars": [], "session": {"flagState": "none"}, "messages": []}
        self.column_spec = []
        self.leader_lap = 0
        self.lap_chart = LaptimeChart()

    def car(self, race_num):
        if race_num not in self._cars:
            self._cars[race_num] = Car(race_num)
        return self._cars[race_num]

    @property
    def cars(self):
        return sorted(self._cars.values(), key=lambda c: tryInt(c.race_num))

    def update_state(self, newState, colSpec, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        if newState["session"].get("flagState", "none") != "none":
            self._update_cars(self.current_state, newState, colSpec, timestamp)
            self._update_session(self.current_state, newState, colSpec, timestamp)
        self.latest_timestamp = timestamp
        self.current_state = copy.deepcopy(newState)
        self.column_spec = colSpec

    def _update_cars(self, oldState, newState, colSpec, timestamp):
        f = FieldExtractor(colSpec)
        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))
        old_flag = FlagStatus.fromString(oldState["session"].get("flagState", "none"))

        pit_states = ["PIT", "FUEL", "N/S"]

        for idx, new_car in enumerate(newState['cars']):
            race_num = f.get(new_car, Stat.NUM)
            if race_num:
                car = self.car(race_num)
                car.current_lap = self._get_lap_count(race_num, new_car, f, newState['cars'])
                new_leader_lap = max(self.leader_lap, car.current_lap)
                if new_leader_lap != self.leader_lap:
                    self.leader_lap = new_leader_lap
                    self.session.flag_change(flag, new_leader_lap, timestamp)
                driver = f.get(new_car, Stat.DRIVER)
                tyre = f.get(new_car, Stat.TYRE)

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
                            car.add_lap(new_lap[0], idx + 1, driver, timestamp, flag, tyre)
                            self.lap_chart.tally(race_num, car.laps[-1])
                    except Exception:  # Non-tuple case (do any services still not use tuples?)
                        if old_lap != new_lap or old_lap_num != new_lap_num:
                            car.add_lap(new_lap, idx + 1, driver, timestamp, flag, tyre)
                            self.lap_chart.tally(race_num, car.laps[-1])

                    old_car_state = f.get(old_car, Stat.STATE)

                    if new_car_state in pit_states and old_car_state not in pit_states:
                        car.pit_in(timestamp)
                    elif new_car_state not in pit_states and old_car_state in pit_states:
                        car.pit_out(timestamp, driver, flag)

                    if new_car_state == "FUEL" and old_car_state != "FUEL":
                        car.fuel_start(timestamp)
                    elif new_car_state != "FUEL" and old_car_state == "FUEL":
                        car.fuel_stop(timestamp)

                    if car.current_stint and (tyre != f.get(old_car, Stat.TYRE) or tyre != car.current_stint.tyre):
                        car.current_stint.tyre = tyre

                    old_driver = f.get(old_car, Stat.DRIVER)
                    if old_driver and old_driver != driver:
                        car.set_driver(driver)

                elif new_car_state not in pit_states:
                    car.pit_out(timestamp, driver, flag)
                else:
                    car.set_driver(driver)

    def _update_session(self, oldState, newState, colSpec, timestamp):
        flag = FlagStatus.fromString(newState["session"].get("flagState", "none"))
        old_flag = FlagStatus.fromString(oldState["session"].get("flagState", "none"))
        if flag != old_flag or not self.session.this_period:
            self.session.flag_change(flag, self.leader_lap, timestamp)

    def _get_lap_count(self, race_num, car, f, cars):
        from_timing = f.get(car, Stat.LAPS)
        if from_timing:
            return int(from_timing)
        else:
            our_num = f.get(car, Stat.NUM)
            # TSNL put lap count in the "gap" column FSR
            leader_gap = f.get(cars[0], Stat.GAP)
            if leader_gap:
                tsnl = TSNL_LAP_HACK_REGEX.match(leader_gap)
                if tsnl:
                    # Work up until we find the lap count relevant to us
                    lap_count = int(tsnl.group(1))
                    for other_car in cars:
                        tsnl = TSNL_LAP_HACK_REGEX.match(f.get(other_car, Stat.GAP))
                        if tsnl:
                            lap_count = int(tsnl.group(1))
                        if f.get(other_car, Stat.NUM) == our_num:
                            return lap_count
            return len(self.car(race_num).laps)


if __name__ == '__main__':
    filename = sys.argv[1]
    dc = None

    if filename.endswith(".data.p"):
        with open(filename, "rb") as data_dump_file:
            dc = cPickle.load(data_dump_file)

    else:
        dc = DataCentre()
        rec = RecordingFile(filename)

        colSpec = Stat.parse_colspec(rec.manifest['colSpec'])

        start_time = time.time()

        for i in range(rec.frames + 1):
            newState = rec.getStateAt(i * int(rec.manifest['pollInterval']))
            dc.update_state(newState, colSpec, rec.manifest['startTime'] + (i * int(rec.manifest['pollInterval'])))
            print "{}/{}".format(i, rec.frames)

        stop_time = time.time()
        print "Processed {} frames in {}s == {:.3f} frames/s".format(rec.frames, stop_time - start_time, rec.frames / (stop_time - start_time))
