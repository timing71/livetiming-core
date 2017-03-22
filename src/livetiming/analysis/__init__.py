from livetiming.analysis.data import DataCentre
from livetiming.network import Message, MessageClass
from lzstring import LZString
from twisted.logger import Logger
import simplejson
import time
import copy


class Analyser(object):
    log = Logger()

    def __init__(self, uuid, publishFunc, modules=[], publish=True):
        for m in modules:
            if not issubclass(m, Analysis):
                raise RuntimeError("Supplied {} is not derived from class Analysis".format(m.__name__))
        self.uuid = uuid
        self.publish = publishFunc
        self.data_centre = DataCentre()
        self.modules = {}
        for mclass in modules:
            self.modules[_fullname(mclass)] = mclass(self.data_centre)
        self.oldState = {"cars": [], "session": {"flagState": "none"}, "messages": []}
        self.doPublish = publish

    def receiveStateUpdate(self, newState, colSpec, timestamp=None):
        self.data_centre.update_state(newState, colSpec, timestamp)
        if timestamp is None:
            timestamp = time.time()

        if newState["session"].get("flagState", "none") != "none":
            for mclass, module in self.modules.iteritems():
                try:
                    module.receiveStateUpdate(self.oldState, newState, colSpec, timestamp)
                    if self.doPublish:
                        self.publish(
                            u"{}/analysis/{}".format(self.uuid, mclass),
                            Message(MessageClass.ANALYSIS_DATA_COMPRESSED, LZString().compressToUTF16(simplejson.dumps(module.getData()))).serialise()
                        )
                except Exception:
                    self.log.failure("Exception while publishing update from analysis module {mclass}: {log_failure}", mclass=mclass)
        self.oldState = copy.deepcopy(newState)

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
            return self.modules[mclass].getData()
        else:
            raise RuntimeError("No such analysis module: {}".format(mclass))

    def reset(self):
        for module in self.modules.values():
            module.reset()
        self.oldState = {"cars": [], "session": {"flagStatus": "none"}, "messages": []}
        self.data_centre.reset()


class Analysis(object):
    def __init__(self, data_centre):
        self.data_centre = data_centre
        self.reset()

    def getName(self):
        raise NotImplementedError

    def getData(self):
        raise NotImplementedError

    def receiveStateUpdate(self, oldState, newState, colSpec):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError


def _fullname(ttype):
    module = ttype.__module__
    if module is None or module == str.__class__.__module__:
        return ttype.__name__
    return module + '.' + ttype.__name__
