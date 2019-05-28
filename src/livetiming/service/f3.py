from livetiming.service.f2 import Service as gpservice, createProtocol


class Service(gpservice):
    attribution = ['Formula Motorsport Ltd', 'http://www.fiaformula3.com/']

    def __init__(self, args, extra_args):
        gpservice.__init__(self, args, extra_args)

    def getClientProtocol(self):
        return createProtocol("F3", self)

    def getName(self):
        return "Formula 3"