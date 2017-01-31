class Analyser(object):
    def __init__(self, modules=[]):
        for m in modules:
            if not issubclass(m, Analysis):
                raise RuntimeError("Supplied {} is not derived from class Analysis".format(m.__name__))

        self.modules = {}
        for mclass in modules:
            self.modules[_fullname(mclass)] = mclass()
        self.oldState = None

    def receiveStateUpdate(self, newState, colSpec):
        if self.oldState:
            for module in self.modules:
                module.receiveStateUpdate(self.oldState, newState, colSpec)
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

    def receiveStateUpdate(self, newState, colSpec):
        raise NotImplementedError


def _fullname(ttype):
    module = ttype.__module__
    if module is None or module == str.__class__.__module__:
        return ttype.__name__
    return module + '.' + ttype.__name__
