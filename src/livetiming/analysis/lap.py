from livetiming.racing import Stat
from livetiming.analysis import map_stint_with, per_car

import math


@per_car
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp):
    if old_car:
        old_lap = f.get(old_car, Stat.LAST_LAP)
        new_lap = f.get(new_car, Stat.LAST_LAP)
        old_lap_num = f.get(old_car, Stat.LAPS)
        new_lap_num = f.get(new_car, Stat.LAPS)
        driver = f.get(new_car, Stat.DRIVER)
        tyre = f.get(new_car, Stat.TYRE)

        car = dc.car(race_num)

        try:
            if old_lap[0] != new_lap[0] or old_lap_num != new_lap_num:
                car.current_lap = _get_lap_count(car, new_car, f, dc.current_state['cars'])
                car.add_lap(new_lap[0], position, driver, timestamp, flag, tyre)
                dc.lap_chart.tally(race_num, car.laps[-1])
                print "New lap!", car.current_lap
                return True
        except Exception:  # Non-tuple case (do any services still not use tuples?)
            if old_lap != new_lap or old_lap_num != new_lap_num:
                car.current_lap = _get_lap_count(car, new_car, f, dc.current_state['cars'])
                car.add_lap(new_lap, position, driver, timestamp, flag, tyre)
                dc.lap_chart.tally(race_num, car.laps[-1])
                print "New lap (old way)!"
                return True

    return False


def get_data(dc):
    return {car.race_num: [map_stint_with(car, dc.latest_timestamp)(car.current_stint), car.last_pass] for car in dc._cars.values()}


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
