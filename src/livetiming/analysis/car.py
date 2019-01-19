from livetiming.racing import Stat
from livetiming.analysis import per_car


@per_car
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp):
    if race_num not in dc._cars:
        c = dc.car(race_num)
        c.race_class = f.get(new_car, Stat.CLASS)
        c.team = f.get(new_car, Stat.TEAM)
        c.vehicle = f.get(new_car, Stat.CAR)
        return True
    return False


def get_data(dc, offline_mode):
    return {car.race_num: car.for_json() for car in dc._cars.values()}
