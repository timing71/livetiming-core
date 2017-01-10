from autobahn.twisted.websocket import WebSocketClientProtocol,\
    WebSocketClientFactory, connectWS

from livetiming.service import Service as lt_service
from lzstring import LZString

import simplejson
import urllib2
from livetiming.racing import FlagStatus


def getToken():
    tokenData = simplejson.load(urllib2.urlopen("https://livetiming.getraceresults.com/lt/negotiate?clientProtocol=1.5"))
    print tokenData
    return (tokenData["ConnectionId"], tokenData["ConnectionToken"])


def getWebSocketURL(tk, tkdm, token):
    return "wss://livetiming.getraceresults.com/lt/connect?transport=webSockets&clientProtocol=1.5&_tk={}&_gr=w&_tkdm={}&connectionToken={}&tid=8".format(tk, tkdm, urllib2.quote(token[1]))


def create_protocol(service):
    class TimeserviceNLClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            print u"Connected: {}".format(response)

        def onMessage(self, payload, isBinary):
            data = simplejson.loads(payload)
            if "M" in data:
                for message in data["M"]:
                    self.handleMessage(message)

        def handleMessage(self, message):
            msgType, body = message
            if msgType == "_":
                initialState = simplejson.loads(LZString().decompressFromUTF16(body))
                for submessage in initialState:
                    self.handleMessage(submessage)
            elif hasattr(service, msgType) and callable(getattr(service, msgType)):
                getattr(service, msgType)(body)
            elif msgType == "a_i":
                # stats - ignore
                print "a_i", body
            else:
                print "Unknown message {}: {}".format(msgType, body)

        def onClose(self, wasClean, code, reason):
            print "Closed"
    return TimeserviceNLClientProtocol


def mapCar(car):
    return [
        car[2],
        mapState(car[1]),
        car[6],
        car[18],
        car[4],
        car[20],
        car[13],
        parseTime(car[10]),
        parseTime(car[11]),
        [parseTime(car[15])],
        [parseTime(car[16])],
        [parseTime(car[17])],
        [parseTime(car[12])],
        [parseTime(car[8])],
        car[9],
        int(car[0])  # position
    ]


def mapState(raw):
    mapp = {
        "0": "RUN",
        "1": "RUN",
        "2": "RUN",
        "3": "RUN",
        "5": "PIT",
        "6": "N/S",
        "11": "OUT",
        "12": "FUEL"
    }
    if raw in mapp:
        return mapp[raw]
    else:
        return raw


def mapFlag(raw):
    mapp = {
        2: FlagStatus.RED,
        3: FlagStatus.SC,
        4: FlagStatus.CODE_60,
        5: FlagStatus.CHEQUERED,
        6: FlagStatus.GREEN,
        7: FlagStatus.FCY,
    }
    try:
        if int(raw) in mapp:
            return mapp[int(raw)].name.lower()
    except:
        pass
    return "none"


def parseTime(raw):
    if raw == "9223372036854775807":
        return ""
    try:
        return int(raw) / 1000000.0
    except:
        return raw


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        socketURL = getWebSocketURL("17047960b73e48c4a899f43a2459cc20", "41798", getToken())
        factory = WebSocketClientFactory(socketURL)
        factory.protocol = create_protocol(self)
        connectWS(factory)

        self.carState = []
        self.sessionState = {"flagState": "none"}

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Class", "class"),
            ("Team", "text"),
            ("Driver", "text"),
            ("Car", "text"),
            ("Laps", "numeric"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("S1", "time"),
            ("S2", "time"),
            ("S3", "time"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "num")
        ]

    def r_i(self, body):
        if 'r' in body:
            table = {}
            for cellspec in body['r']:
                if cellspec[0] not in table:
                    table[cellspec[0]] = {}
                table[cellspec[0]][cellspec[1]] = cellspec[2]
            self.carState = table

    def h_h(self, body):
        if "f" in body:
            self.sessionState["flagState"] = mapFlag(body["f"])
        if "ll" in body:
            self.sessionState["lapsCompleted"] = int(body['ll'])
        print "h_h", body

    def h_i(self, body):
        self.h_h(body)

    def r_c(self, body):
        for update in body:
            if update[0] != -1 and update[1] != -1:
                self.carState[update[0]][update[1]] = update[2]

    def getRaceState(self):
        state = {
            "cars": sorted(map(mapCar, self.carState.values()), key=lambda c: c[-1]),
            "session": self.sessionState
        }
        return state
