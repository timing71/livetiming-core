from collections import defaultdict, OrderedDict
from livetiming.racing import Stat, FlagStatus
from livetiming.recording import RecordingFile
import cPickle
import copy
import re
import sys
import time
import math


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
            # self.lap_num,
            self.laptime,
            # self.position,
            # self.driver,
            # self.timestamp,
            self.flag,
            # self.tyre
        ]

    def __repr__(self, *args, **kwargs):
        return u"<Lap {}: {} pos {} {} {} {}>".format(*self.for_json())


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

    @property
    def best_lap_time(self):
        return min(map(lambda l: l.laptime, self.laps)) if len(self.laps) > 0 else None

    @property
    def average_lap_time(self):
        if len(self.laps) == 1:
            return None
        if self.in_progress:
            # Exclude first lap (out lap)
            return sum(map(lambda l: l.laptime, self.laps[1:])) / (len(self.laps) - 1)
        else:
            # Exclude first (out) and last (in) laps
            if len(self.laps) == 2:
                return None
            return sum(map(lambda l: l.laptime, self.laps[1:-1])) / (len(self.laps) - 2)

    def __repr__(self, *args, **kwargs):
        return u"<Stint: {} laps {}-{} time {}-{} yellows {} in progress? {} >".format(
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
        self.current_lap = 1
        self._current_lap_flags = [FlagStatus.NONE]
        self.initial_driver = None
        self.fuel_times = []
        self.last_pass = None
        self.drivers = []

        # Public static data
        self.race_class = None
        self.team = None
        self.vehicle = None

    def add_lap(self, laptime, position, driver, timestamp, current_flag=FlagStatus.NONE, tyre=None):
        max_flag = max(self._current_lap_flags)

        if not (self.current_stint or self.inPit):
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

            if self.inPit and self.stints:
                # Sometimes the finish line is crossed in the pit lane - the lap should be added to the previous stint
                prev_stint = self.stints[-1]
                prev_stint.laps.append(self.laps[-1])
                prev_stint.end_lap = self.current_lap
            elif self.current_stint:
                self.current_stint.laps.append(self.laps[-1])
        self._current_lap_flags = [current_flag]
        self.last_pass = timestamp

    def see_flag(self, flag):
        self._current_lap_flags.append(flag)

    def set_driver(self, driver):
        if self.current_stint:
            self.current_stint.driver = driver
        else:
            self.initial_driver = driver
        if driver not in self.drivers:
            self.drivers.append(driver)

    def pit_in(self, timestamp):
        if len(self.stints) > 0:
            currentStint = self.stints[-1]
            currentStint.finish(self.current_lap, timestamp)
        self.inPit = True

    def pit_out(self, timestamp, driver, flag):
        if self.inPit:
            prev_stint_end_lap = self.stints[-1].end_lap if self.stints and self.stints[-1].end_lap else self.current_lap - 1
            self.stints.append(Stint(max(1, prev_stint_end_lap + 1), timestamp, driver, flag))
            self.inPit = False

    def fuel_start(self, timestamp):
        self.fuel_times.append([timestamp, None])

    def fuel_stop(self, timestamp):
        if self.fuel_times:
            self.fuel_times[-1][1] = timestamp

    @property
    def current_stint(self):
        if len(self.stints) > 0:
            latest = self.stints[-1]
            if latest.in_progress:
                return latest
        return None

    def driver_name(self):
        try:
            return next(iter(self.drivers))
        except StopIteration:
            return ""

    def for_json(self):
        return [self.race_class, self.team, self.vehicle]


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

    def flag_change(self, new_flag, timestamp):
        self.session.flag_change(new_flag, self.leader_lap, timestamp)
        for car in self._cars.values():
            car.see_flag(new_flag)

    def car(self, race_num):
        if race_num not in self._cars:
            self._cars[race_num] = Car(race_num)
        return self._cars[race_num]


if __name__ == '__main__':
    filename = sys.argv[1]
    dc = None

    if filename.endswith(".data.p"):
        with open(filename, "rb") as data_dump_file:
            dc = cPickle.load(data_dump_file)
