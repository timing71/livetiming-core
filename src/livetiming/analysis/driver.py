from livetiming.racing import Stat
from livetiming.analysis import per_car


@per_car
def receive_state_update(dc, race_num, old_car, new_car, f, flag, timestamp):
    old_driver = f.get(old_car, Stat.DRIVER)
    new_driver = f.get(new_car, Stat.DRIVER)

    if old_driver != new_driver or race_num not in dc._cars:
        c = dc.car(race_num)
        is_new = new_driver not in c.drivers
        c.set_driver(new_driver)
        return is_new
    return False


def get_data(dc):
    return {car.race_num: car.drivers for car in dc._cars.values()}
