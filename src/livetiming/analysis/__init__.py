class Analyser(object):
    def __init__(self, modules=[]):
        self.modules = map(lambda m: m(), modules)
        self.oldState = None

    def receiveStateUpdate(self, newState, colSpec):
        if self.oldState:
            for module in self.modules:
                module.receiveStateUpdate(self.oldState, newState, colSpec)
        self.oldState = newState
