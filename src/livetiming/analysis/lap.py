from livetiming.racing import Stat
from livetiming.analysis import map_stint_with, per_car

import math
import re


@per_car
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp):
    if old_car:
        old_lap = f.get(old_car, Stat.LAST_LAP)
        new_lap = f.get(new_car, Stat.LAST_LAP)
        old_lap_num = f.get(old_car, Stat.LAPS)
        new_lap_num = f.get(new_car, Stat.LAPS)

        car = dc.car(race_num)

        try:
            if old_lap[0] != new_lap[0] or old_lap_num != new_lap_num:
                _apply_car_lap(dc, race_num, car, new_car, new_lap[0], position, f, timestamp, flag)
                return True
        except Exception:  # Non-tuple case (do any services still not use tuples?)
            if old_lap != new_lap or old_lap_num != new_lap_num:
                _apply_car_lap(dc, race_num, car, new_car, new_lap, position, f, timestamp, flag)
                return True

    return False


def _apply_car_lap(dc, race_num, car, new_car, new_lap, position, f, timestamp, flag):
    driver = f.get(new_car, Stat.DRIVER)
    tyre = f.get(new_car, Stat.TYRE)
    car.current_lap = _get_lap_count(car, new_car, f, dc.current_state['cars'])
    car.add_lap(new_lap, position, driver, timestamp, flag, tyre)
    if len(car.laps) > 0:
        dc.lap_chart.tally(race_num, car.laps[-1])

    new_leader_lap = max(dc.leader_lap, car.current_lap)
    if new_leader_lap != dc.leader_lap:
        dc.leader_lap = new_leader_lap
        dc.session.flag_change(flag, new_leader_lap, timestamp)


def get_data(dc):
    return {car.race_num: [map_stint_with(car, dc.latest_timestamp)(car.current_stint), car.last_pass] for car in dc._cars.values()}

TSNL_LAP_HACK_REGEX = re.compile("\(([0-9]+) laps?")


def _get_lap_count(car, new_car, f, cars):
    from_timing = f.get(new_car, Stat.LAPS)
    if from_timing:
        try:
            return math.floor(float(from_timing))
        except ValueError:
            pass
    our_num = f.get(new_car, Stat.NUM)
    # TSNL put lap count in the "gap" column FSR
    leader_gap = f.get(cars[0], Stat.GAP)
    if leader_gap:
        tsnl = TSNL_LAP_HACK_REGEX.match(str(leader_gap))
        if tsnl:
            # Work up until we find the lap count relevant to us
            lap_count = int(tsnl.group(1))
            for other_car in cars:
                tsnl = TSNL_LAP_HACK_REGEX.match(str(f.get(other_car, Stat.GAP)))
                if tsnl:
                    lap_count = int(tsnl.group(1))
                if f.get(other_car, Stat.NUM) == our_num:
                    return lap_count
    return len(car.laps)
