from livetiming.racing import Stat
from livetiming.analysis import per_car

PIT_STATES = ["PIT", "FUEL", "N/S"]


@per_car
def receive_state_update(dc, race_num, old_car, new_car, f, flag, timestamp):
    old_car_state = f.get(old_car, Stat.STATE)
    new_car_state = f.get(new_car, Stat.STATE)
    car = dc.car(race_num)

    driver = f.get(new_car, Stat.DRIVER)

    has_changed = False

    if new_car_state in PIT_STATES and old_car_state not in PIT_STATES:
        car.pit_in(timestamp)
        has_changed = True
    elif new_car_state not in PIT_STATES and (old_car_state in PIT_STATES or old_car_state is None):
        car.pit_out(timestamp, driver, flag)
        has_changed = True

    if new_car_state == "FUEL" and old_car_state != "FUEL":
        car.fuel_start(timestamp)
        has_changed = True
    elif new_car_state != "FUEL" and old_car_state == "FUEL":
        car.fuel_stop(timestamp)
        has_changed = True

    return has_changed


def get_data(dc):
    return {car.race_num: map(_map_stint_with(car, dc.latest_timestamp), car.stints) for car in dc._cars.values()}


def _map_stint_with(car, timestamp):
    drivers = car.drivers

    def map_stint(stint):
        return [
            stint.start_lap,
            stint.start_time,
            stint.end_lap if not stint.in_progress else car.current_lap,
            stint.end_time if not stint.in_progress else timestamp,
            stint.in_progress,
            drivers.index(stint.driver) if stint.driver in drivers else -1,
            stint.yellow_laps
        ]
    return map_stint
