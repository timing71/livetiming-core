from livetiming.racing import Stat
from livetiming.analysis import per_car


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
                car.add_lap(new_lap[0], position, driver, timestamp, flag, tyre)
                dc.lap_chart.tally(race_num, car.laps[-1])
        except Exception:  # Non-tuple case (do any services still not use tuples?)
            if old_lap != new_lap or old_lap_num != new_lap_num:
                car.add_lap(new_lap, position, driver, timestamp, flag, tyre)
                dc.lap_chart.tally(race_num, car.laps[-1])

    return False  # We don't want to send out lap data from this module - as it quickly gets huge


def get_data(dc):
    return None
