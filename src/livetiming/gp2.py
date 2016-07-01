from autobahn.twisted.websocket import connectWS, WebSocketClientFactory, WebSocketClientProtocol
from datetime import datetime
from livetiming.racing import FlagStatus
from livetiming.service import Service as lt_service

import simplejson
import urllib2


def getToken():
    tokenData = simplejson.load(urllib2.urlopen("http://gpserieslivetiming.cloudapp.net/streaming/negotiate?clientProtocol=1.5"))
    return (tokenData["ConnectionId"], tokenData["ConnectionToken"])


def getWebSocketURL(token):
    return "ws://gpserieslivetiming.cloudapp.net/streaming/connect?transport=webSockets&clientProtocol=1.5&connectionToken={}&connectionData=%5B%7B%22name%22%3A%22streaming%22%7D%5D&tid=9".format(urllib2.quote(token[1]))


connector = None


class GP2ClientProtocol(WebSocketClientProtocol):

    def onConnect(self, response):
        print u"Connected: {}".format(response)

    def onOpen(self):
        self.sendMessage('{H: "streaming", M: "JoinFeeds", A: ["GP2", ["data", "weather", "status", "time"]], I: 0}')
        self.sendMessage('{"H":"streaming","M":"GetData2","A":["GP2",["data","statsfeed","weatherfeed","sessionfeed","trackfeed","timefeed"]],"I":1}')

    def onMessage(self, payload, isBinary):
        global connector
        if connector is not None:
            connector.onTimingPayload(simplejson.loads(payload.decode('utf8')))


def parseState(rawState):
    if rawState["InPit"] == 1:
        return "PIT"
    elif rawState["PitOut"] == 1:
        return "OUT"
    elif rawState["Retired"] == 1 or rawState["Stopped"] == 1:
        return "RET"
    return "RUN"


def parseTime(timeBlock):
    try:
        ttime = datetime.strptime(timeBlock["Value"], "%S.%f")
        timeVal = ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        try:
            ttime = datetime.strptime(timeBlock["Value"], "%M:%S.%f")
            timeVal = (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            timeVal = "" if timeBlock["Value"] == "." else timeBlock["Value"]

    flag = "pb" if "PersonalFastest" in timeBlock and timeBlock["PersonalFastest"] == 1 else "sb" if "OverallFastest" in timeBlock and timeBlock["OverallFastest"] == 1 else ""

    return (timeVal, flag)


def parseFlag(rawFlag):
    flagMap = {
        "Finished": FlagStatus.CHEQUERED,
        "Finalised": FlagStatus.CHEQUERED,
    }
    if rawFlag in flagMap:
        return flagMap[rawFlag].name.lower()
    return "none"


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        global connector
        connector = self
        socketURL = getWebSocketURL(getToken())
        factory = WebSocketClientFactory(socketURL)
        factory.protocol = GP2ClientProtocol

        connectWS(factory)

        self.carState = []
        self.sessionState = {}

    def getName(self):
        return "GP2"

    def getDescription(self):
        return "GP2"

    def getPollInterval(self):
        return 1

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Driver", "text"),
            ("Lap", "num"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("S1", "time"),
            ("S2", "time"),
            ("S3", "time"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "num")
        ]

    def onTimingPayload(self, payload):
        if "M" in payload:
            for message in payload["M"]:
                self.handleTimingMessage(message)
        elif "R" in payload:
            if "data" in payload["R"]:
                self.carState = []
                carList = payload["R"]["data"][2].itervalues()
                self.carState = []
                for car in sorted(carList, key=lambda car: int(car["position"]["Value"])):
                    self.carState.append([
                        car["driver"]["RacingNumber"],
                        parseState(car["status"]),
                        car["driver"]["FullName"],
                        car["laps"]["Value"],
                        car["gapP"]["Value"],
                        car["intervalP"]["Value"],
                        parseTime(car["sectors"][0]),
                        parseTime(car["sectors"][1]),
                        parseTime(car["sectors"][2]),
                        parseTime(car["last"]),
                        parseTime(car["best"]),
                        car["pits"]["Value"]
                    ])
            if "sessionfeed" in payload["R"]:
                print parseFlag(payload["R"]["sessionfeed"][1]["Value"])
                self.sessionState["flagState"] = parseFlag(payload["R"]["sessionfeed"][1]["Value"])
        else:
            print "What is {}?".format(payload)

    def handleTimingMessage(self, message):
        print "Message of type {}".format(message["M"])

    def getRaceState(self):
        return {"cars": self.carState, "session": self.sessionState}
