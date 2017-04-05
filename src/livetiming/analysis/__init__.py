from livetiming.analysis.data import DataCentre
from livetiming.network import Message, MessageClass
from lzstring import LZString
from twisted.logger import Logger
import simplejson
import time
import copy
import cPickle


class Analyser(object):
    log = Logger()

    def __init__(self, uuid, publishFunc, modules=[], publish=True):
        for m in modules:
            if not issubclass(m, Analysis):
                raise RuntimeError("Supplied {} is not derived from class Analysis".format(m.__name__))
        self.uuid = uuid
        self.publish = publishFunc
        self._load_data_centre()
        self.modules = {}
        for mclass in modules:
            self.modules[_fullname(mclass)] = mclass(self.data_centre)
        self.doPublish = publish

    def receiveStateUpdate(self, newState, colSpec, timestamp=None):
        self.data_centre.update_state(newState, colSpec, timestamp)

        if self.doPublish and newState["session"].get("flagState", "none") != "none":
            for mclass, module in self.modules.iteritems():
                try:
                    self.publish(
                        u"{}/analysis/{}".format(self.uuid, mclass),
                        Message(MessageClass.ANALYSIS_DATA_COMPRESSED, LZString().compressToUTF16(simplejson.dumps(module.getData()))).serialise()
                    )
                except Exception:
                    self.log.failure("Exception while publishing update from analysis module {mclass}: {log_failure}", mclass=mclass)

    def save_data_centre(self):
        with open("{}.data.p".format(self.uuid), "wb") as data_dump_file:
            cPickle.dump(self.data_centre, data_dump_file, cPickle.HIGHEST_PROTOCOL)

    def _load_data_centre(self):
        try:
            with open("{}.data.p".format(self.uuid), "rb") as data_dump_file:
                self.data_centre = cPickle.load(data_dump_file)
                self.log.info("Using existing data centre dump from {}.dump.p".format(self.uuid))
        except IOError:
            self.data_centre = DataCentre()

    def getManifest(self):
        manifest = []
        for mclass, module in self.modules.iteritems():
            manifest.append((mclass, module.getName()))
        return manifest

    def getData(self, mclass=None):
        if mclass is None:
            allData = {}
            for clz, module in self.modules.iteritems():
                allData[clz] = module.getData()
            return allData
        elif mclass in self.modules:
            d = self.modules[mclass].getData()
            return simplejson.loads(simplejson.dumps(d))  # HACK HACK HACK - why does session data fail when we don't do this?
        else:
            raise RuntimeError("No such analysis module: {}".format(mclass))

    def getCars(self):
        return map(lambda car: (car.race_num, car.driver_name()), self.data_centre.cars)

    def reset(self):
        self.data_centre.reset()


class Analysis(object):
    def __init__(self, data_centre):
        self.data_centre = data_centre

    def getName(self):
        raise NotImplementedError

    def getData(self):
        raise NotImplementedError


def _fullname(ttype):
    module = ttype.__module__
    if module is None or module == str.__class__.__module__:
        return ttype.__name__
    return module + '.' + ttype.__name__
