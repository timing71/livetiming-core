from autobahn.twisted.websocket import WebSocketClientProtocol,\
    WebSocketClientFactory, connectWS

from livetiming.service import Service as lt_service
from lzstring import LZString

import simplejson
import urllib2
from livetiming.racing import FlagStatus
from datetime import datetime
import time


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
                print msgType
                getattr(service, msgType)(body)
            elif msgType == "a_i":
                # stats - ignore
                pass
            else:
                print "Unknown message {}: {}".format(msgType, body)

        def onClose(self, wasClean, code, reason):
            print "Closed"
    return TimeserviceNLClientProtocol


def mapCar(car):

    mappedCar = [
        car[2][0],
        mapState(car[1][0]),
        car[6][0],
        car[18][0],
        car[4][0],
        car[20][0],
        car[13][0],
        parseTime(car[10][0]),
        parseTime(car[11][0]),
        [parseTime(car[15][0]), mapTimeFlags(car[15][1])],
        [parseTime(car[16][0]), mapTimeFlags(car[16][1])],
        [parseTime(car[17][0]), mapTimeFlags(car[17][1])],
        [parseTime(car[12][0]), mapTimeFlags(car[12][1])],
        [parseTime(car[8][0]), mapTimeFlags(car[8][1])],
        car[9][0],
        int(car[0][0])  # position
    ]

    if mappedCar[12][1] == "sb" and mappedCar[12][0] == mappedCar[13][0]:
        mappedCar[12][1] = "sb-new"

    return mappedCar


def mapTimeFlags(flag):
    if flag == "65280":
        return 'pb'
    if flag == "16736511":
        return 'sb'
    return ""


def mapState(raw):
    mapp = {
        "0": "RUN",
        "1": "RUN",
        "2": "RUN",
        "3": "RUN",
        "4": "FIN",
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


def serverToRealTime(serverTime):
    timeFactor = 10957 * 24 * 60 * 60 * 1000
    return ((serverTime / 1000) + timeFactor) / 1000


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        socketURL = getWebSocketURL("17047960b73e48c4a899f43a2459cc20", "41798", getToken())
        factory = WebSocketClientFactory(socketURL)
        factory.protocol = create_protocol(self)
        connectWS(factory)

        self.carState = []
        self.sessionState = {"flagState": "none"}
        self.timeOffset = None

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
                table[cellspec[0]][cellspec[1]] = (cellspec[2], None) if len(cellspec) == 3 else (cellspec[2], cellspec[3])
            self.carState = table
        # TODO parse column headers from body['l']['h']
        # We should probably generate column spec from it

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

    def s_t(self, serverTime):
        self.timeOffset = serverToRealTime(serverTime) - time.mktime(datetime.utcnow().utctimetuple())
        self.log.info("Set time offset to {}".format(self.timeOffset))

    def getRaceState(self):
        state = {
            "cars": sorted(map(mapCar, self.carState.values()), key=lambda c: c[-1]),
            "session": self.sessionState
        }
        return state
