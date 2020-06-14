from livetiming.analysis import PROCESSING_MODULES
from livetiming.analysis.data import *

import pickle
import importlib
import simplejson


def _dump_dc(dc):
    modules = {m: importlib.import_module("livetiming.analysis.{}".format(m)) for m in PROCESSING_MODULES}
    data = {k: module.get_data(dc) for k, module in modules.items()}
    data['state'] = dc.current_state

    car_stats = data.pop('car')
    for k, v in car_stats.items():
        data[k] = v

    print(simplejson.dumps(data, separators=(',', ':')))


if __name__ == '__main__':
    filename = sys.argv[1]
    dc = None

    if filename.endswith(".data.p"):
        with open(filename, "rb") as data_dump_file:
            dc = pickle.load(data_dump_file)

        _dump_dc(dc)
