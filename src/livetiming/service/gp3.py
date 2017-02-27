from livetiming.service.gp2 import Service as gpservice, createProtocol


class Service(gpservice):
    def __init__(self, config):
        gpservice.__init__(self, config)

    def getClientProtocol(self):
        return createProtocol("GP3", self)

    def getName(self):
        return "GP3"

    def getDefaultDescription(self):
        return "GP3"
