from livetiming.service.gp2 import Service as gpservice, createProtocol


class Service(gpservice):
    def __init__(self, args, extra_args):
        gpservice.__init__(self, args, extra_args)

    def getClientProtocol(self):
        return createProtocol("GP3", self)

    def getName(self):
        return "GP3"