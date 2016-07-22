from autobahn.twisted.websocket import WebSocketClientProtocol
from livetiming.gp2 import Service as gpservice

import simplejson


connector = None


class GP3ClientProtocol(WebSocketClientProtocol):

    def onConnect(self, response):
        print u"Connected: {}".format(response)

    def onOpen(self):
        self.sendMessage('{H: "streaming", M: "JoinFeeds", A: ["GP3", ["data", "weather", "status", "time"]], I: 0}')
        self.sendMessage('{"H":"streaming","M":"GetData2","A":["GP3",["data","statsfeed","weatherfeed","sessionfeed","trackfeed","timefeed"]],"I":1}')

    def onMessage(self, payload, isBinary):
        global connector
        if connector is not None:
            connector.onTimingPayload(simplejson.loads(payload.decode('utf8')))


class Service(gpservice):
    def __init__(self, config):
        gpservice.__init__(self, config)
        global connector
        connector = self

    def getClientProtocol(self):
        return GP3ClientProtocol

    def getName(self):
        return "GP3"

    def getDescription(self):
        return "GP3"

    def getWSHeaders(self):
        return {
            "Origin": "http://www.gp3series.com",
            "Referer": "http://www.gp3series.com/Live-Timing/Live-Timing-Inline/"
        }
