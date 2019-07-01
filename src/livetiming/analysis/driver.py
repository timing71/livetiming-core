from livetiming.racing import Stat
from livetiming.analysis import per_car


def get_data(dc):
    return {car.race_num: car.drivers for car in list(dc._cars.values())}


@per_car('driver', get_data)
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp, new_messages):
    old_driver = f.get(old_car, Stat.DRIVER)
    new_driver = f.get(new_car, Stat.DRIVER)

    if old_driver != new_driver or race_num not in dc._cars:
        c = dc.car(race_num)
        is_new = new_driver not in c.drivers
        c.set_driver(new_driver)
        return is_new
    return False
