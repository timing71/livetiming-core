from livetiming.service.f2 import Service as gpservice, createProtocol


class Service(gpservice):
    attribution = ['FOWC', 'http://www.gp3series.com/']

    def __init__(self, args, extra_args):
        gpservice.__init__(self, args, extra_args)

    def getClientProtocol(self):
        return createProtocol("GP3", self)

    def getName(self):
        return "GP3"
