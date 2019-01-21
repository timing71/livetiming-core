from livetiming.racing import FlagStatus, Stat
from livetiming.analysis import FieldExtractor, per_car

import importlib


SUBMODULES = {m: importlib.import_module("livetiming.analysis.{}".format(m)) for m in ['lap', 'stint']}


def get_data(dc, offline_mode):
    return {car.race_num: car.for_json() for car in dc._cars.values()}


def receive_state_update(dc, old_state, new_state, colspec, timestamp):
    flag = FlagStatus.fromString(new_state["session"].get("flagState", "none"))
    f = FieldExtractor(colspec)
    result = []
    for idx, new_car in enumerate(new_state['cars']):
        race_num = f.get(new_car, Stat.NUM)
        if race_num:
            old_car = next(iter([c for c in old_state["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)

            for module in SUBMODULES.values():
                update = module.receive_state_update(dc, race_num, idx + 1, old_car, new_car, f, flag, timestamp)
                if update:
                    result.append(update)

    return result
