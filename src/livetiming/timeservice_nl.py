from autobahn.twisted.websocket import WebSocketClientProtocol,\
    WebSocketClientFactory, connectWS

from livetiming.service import Service as lt_service
from lzstring import LZString

import simplejson
import urllib2
from livetiming.racing import FlagStatus
from datetime import datetime
import time
from livetiming.messages import TimingMessage, CarPitMessage,\
    DriverChangeMessage, FastLapMessage


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
        car[19][0],
        car[4][0],
        car[21][0],
        parseTime(car[8][0]),
        parseTime(car[9][0]),
        [parseTime(car[16][0]), mapTimeFlags(car[16][1])],
        [parseTime(car[17][0]), mapTimeFlags(car[17][1])],
        [parseTime(car[18][0]), mapTimeFlags(car[18][1])],
        [parseTime(car[10][0]), mapTimeFlags(car[10][1])],
        [parseTime(car[11][0]), mapTimeFlags(car[11][1])],
        car[12][0],
        int(car[0][0])  # position
    ]

    if mappedCar[10][1] == "sb" and mappedCar[10][0] == mappedCar[11][0]:
        mappedCar[11][1] = "sb-new"

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


timeFactor = 10957 * 24 * 60 * 60 * 1000


def utcnow():
    return time.mktime(datetime.utcnow().utctimetuple())


def serverToRealTime(serverTime, offset=0):
    if offset is None:
        offset = 0
    return (((serverTime / 1000) + timeFactor) / 1000) - offset


def realToServerTime(realTime):
    return (realTime * 1000 - timeFactor) * 1000


class RaceControlMessage(TimingMessage):
    def __init__(self, messageList):
        self.messageList = messageList

    def _consider(self, oldState, newState):
        if len(self.messageList) > 0:
            return ["Race Control", self.messageList.pop(), "raceControl"]


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
        self.times = {}

        self.messages = []

        self.description = "24H Series"

    def getName(self):
        return "24H Series"

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Class", "class"),
            ("Team", "text"),
            ("Driver", "text"),
            ("Car", "text"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("S1", "time"),
            ("S2", "time"),
            ("S3", "time"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "num")
        ]

    def getPollInterval(self):
        return 1

    def a_r(self, body):
        # clear stats
        self.times = {}
        self.sessionState = {"flagState": "none"}

    def a_u(self, body):
        # best lap history - ignore
        pass

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
        if "q" in body:
            self.times['q'] = int(body['q'])
        if "r" in body:
            self.times['r'] = int(body['r'])
        if "s" in body:
            self.times['s'] = int(body['s'])
        if "e" in body:
            self.times['e'] = int(body['e'])
        if "lt" in body:
            self.times['lt'] = int(body['lt'])
        if "h" in body:
            self.times['h'] = body['h']
        if "n" in body:
            self.description = body["n"]
            self.publishManifest()

    def h_i(self, body):
        self.h_h(body)

    def m_c(self, body):
        # race control message
        if 'Id' in body and 't' in body:
            self.messages.append(body['t'])

    def r_c(self, body):
        for update in body:
            if update[0] != -1 and update[1] != -1 and update[0] in self.carState.keys():
                if update[1] == 0:
                    print "Received position update {}".format(update)
                self.carState[update[0]][update[1]] = (update[2], None) if len(update) == 3 else (update[2], update[3])

    def s_t(self, serverTime):
        self.timeOffset = serverToRealTime(serverTime) - utcnow()
        self.log.info("Set time offset to {}".format(self.timeOffset))

    def t_p(self, body):
        # track position - ignore
        pass

    def getRaceState(self):
        if "lt" in self.times and "r" in self.times and "q" in self.times and self.timeOffset:
            if "h" in self.times and self.times["h"]:
                self.sessionState['timeRemain'] = self.times['r'] / 1000000
            else:
                serverNow = realToServerTime(utcnow() + self.timeOffset)
                elapsed = (serverNow - self.times['q'] + self.times['r'])
                self.sessionState['timeElapsed'] = elapsed / 1000000
                self.sessionState['timeRemain'] = (self.times['lt'] - elapsed) / 1000000
        state = {
            "cars": sorted(map(mapCar, self.carState.values()), key=lambda c: c[-1]),
            "session": self.sessionState
        }
        return state

    def getMessageGenerators(self):
        return super(Service, self).getMessageGenerators() + [
            CarPitMessage(lambda c: c[1], lambda c: c[2], lambda c: c[4]),
            DriverChangeMessage(lambda c: c[2], lambda c: c[4]),
            FastLapMessage(lambda c: c[11], lambda c: c[2], lambda c: c[4]),
            RaceControlMessage(self.messages)
        ]
