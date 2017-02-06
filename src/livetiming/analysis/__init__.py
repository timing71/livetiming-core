from livetiming.network import Message, MessageClass
import time


class Analyser(object):
    def __init__(self, uuid, publishFunc, modules=[]):
        for m in modules:
            if not issubclass(m, Analysis):
                raise RuntimeError("Supplied {} is not derived from class Analysis".format(m.__name__))
        self.uuid = uuid
        self.publish = publishFunc
        self.modules = {}
        for mclass in modules:
            self.modules[_fullname(mclass)] = mclass()
        self.oldState = {"cars": [], "session": {"flagStatus": "none"}, "messages": []}

    def receiveStateUpdate(self, newState, colSpec, timestamp=time.time()):
        for mclass, module in self.modules.iteritems():
            module.receiveStateUpdate(self.oldState, newState, colSpec, timestamp)
            self.publish(
                u"{}/analysis/{}".format(self.uuid, mclass),
                Message(MessageClass.ANALYSIS_DATA, module.getData()).serialise()
            )
        self.oldState = newState

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


class Analysis(object):
    def getName(self):
        raise NotImplementedError

    def getData(self):
        raise NotImplementedError

    def receiveStateUpdate(self, oldState, newState, colSpec):
        raise NotImplementedError


def _fullname(ttype):
    module = ttype.__module__
    if module is None or module == str.__class__.__module__:
        return ttype.__name__
    return module + '.' + ttype.__name__
