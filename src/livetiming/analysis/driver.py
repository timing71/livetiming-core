from livetiming.racing import Stat


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.mapping = {}
        for idx, col in enumerate(colSpec):
            self.mapping[col] = idx

    def get(self, car, field, default=None):
        if car:
            try:
                return car[self.mapping[field]]
            except KeyError:
                return default
        return default


def per_car(func):
    def inner(dc, old_state, new_state, colspec, timestamp):
        f = FieldExtractor(colspec)
        result = False
        for idx, new_car in enumerate(new_state['cars']):
            race_num = f.get(new_car, Stat.NUM)
            if race_num:
                old_car = next(iter([c for c in old_state["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)
                result = func(dc, race_num, old_car, new_car, f, timestamp) or result
        return result
    return inner


@per_car
def receive_state_update(dc, race_num, old_car, new_car, f, timestamp):
    old_driver = f.get(old_car, Stat.DRIVER)
    new_driver = f.get(new_car, Stat.DRIVER)

    if old_driver != new_driver or race_num not in dc._cars:
        dc.car(race_num).set_driver(new_driver)
        return True
    return False


def get_data(dc):
    return {car.race_num: car.drivers for car in dc._cars.values()}
