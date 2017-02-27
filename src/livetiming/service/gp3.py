from autobahn.twisted.websocket import WebSocketClientProtocol
from livetiming.service.gp2 import Service as gpservice

import simplejson


class Service(gpservice):
    def __init__(self, config):
        gpservice.__init__(self, config)

    def getClientProtocol(self):
        service = self

        class GP3ClientProtocol(WebSocketClientProtocol):

            def onConnect(self, response):
                print u"Connected: {}".format(response)

            def onOpen(self):
                self.sendMessage('{H: "streaming", M: "JoinFeeds", A: ["GP3", ["data", "weather", "status", "time"]], I: 0}')
                self.sendMessage('{"H":"streaming","M":"GetData2","A":["GP3",["data","statsfeed","weatherfeed","sessionfeed","trackfeed","timefeed"]],"I":1}')

            def onMessage(self, payload, isBinary):
                service.onTimingPayload(simplejson.loads(payload.decode('utf8')))
        return GP3ClientProtocol

    def getName(self):
        return "GP3"

    def getDefaultDescription(self):
        return "GP3"
