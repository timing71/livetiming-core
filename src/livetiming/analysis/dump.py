from livetiming.analysis import PROCESSING_MODULES
from livetiming.analysis.data import *

import importlib
import simplejson


def _dump_dc(dc):
    modules = {m: importlib.import_module("livetiming.analysis.{}".format(m)) for m in PROCESSING_MODULES}
    data = {k: module.get_data(dc) for k, module in modules.iteritems()}
    data['state'] = dc.current_state
    print simplejson.dumps(data, separators=(',', ':'))


if __name__ == '__main__':
    filename = sys.argv[1]
    dc = None

    if filename.endswith(".data.p"):
        with open(filename, "rb") as data_dump_file:
            dc = cPickle.load(data_dump_file)

        _dump_dc(dc)
