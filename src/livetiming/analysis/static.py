from livetiming.racing import Stat
from livetiming.analysis import per_car


def get_data(dc):
    return {car.race_num: car.for_json() for car in list(dc._cars.values())}


@per_car('static', get_data)
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp, new_messages):
    if race_num not in dc._cars:
        c = dc.car(race_num)
        c.race_class = f.get(new_car, Stat.CLASS)
        c.team = f.get(new_car, Stat.TEAM)
        c.vehicle = f.get(new_car, Stat.CAR)
        return True
    return False
