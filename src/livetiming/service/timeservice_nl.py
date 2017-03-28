# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import WebSocketClientProtocol,\
    WebSocketClientFactory, connectWS

from livetiming.service import Service as lt_service
from lzstring import LZString

import simplejson
import urllib2
from livetiming.racing import FlagStatus, Stat
from datetime import datetime
import time
from livetiming.messages import RaceControlMessage
import argparse
from livetiming.analysis.laptimes import LaptimeAnalysis
from livetiming.analysis.pits import PitStopAnalysis
from livetiming.analysis.driver import StintLength


def getToken():
    tokenData = simplejson.load(urllib2.urlopen("https://livetiming.getraceresults.com/lt/negotiate?clientProtocol=1.5"))
    print tokenData
    return (tokenData["ConnectionId"], tokenData["ConnectionToken"])


def getWebSocketURL(tk, token):
    return "wss://livetiming.getraceresults.com/lt/connect?transport=webSockets&clientProtocol=1.5&_tk={}&_gr=w&connectionToken={}&tid=8".format(tk, urllib2.quote(token[1]))


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
            print msgType
            if msgType == "_":
                initialState = simplejson.loads(LZString().decompressFromUTF16(body))
                for submessage in initialState:
                    self.handleMessage(submessage)
            elif hasattr(service, msgType) and callable(getattr(service, msgType)):
                getattr(service, msgType)(body)
            else:
                print "Unknown message {}: {}".format(msgType, body)

        def onClose(self, wasClean, code, reason):
            print "Closed"
    return TimeserviceNLClientProtocol


def mapTimeFlags(flag):
    if flag == "65280":
        return 'pb'
    if flag == "16736511":
        return 'sb'
    if flag == "6579455" or flag == "4210943" or flag == "255":
        # not sure that 'slow' is accurate but TSNL displays these in red
        return 'slow'
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
        "8": "?",
        "11": "OUT",
        "12": "FUEL"
    }
    if raw in mapp:
        return mapp[raw]
    else:
        print "Unknown state value {}".format(raw)
        return raw


def mapFlag(raw):
    print "Flag: {}".format(raw)
    mapp = {
        1: FlagStatus.NONE,  # Ready to start
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
    except Exception:
        pass
    print "Unknown flag value {}".format(raw)
    return "none"


def parseTime(raw):
    if raw == "9223372036854775807":
        return ""
    try:
        return int(raw) / 1000000.0
    except Exception:
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


def ident(val):
    return val[0]


def shorten(nameTuple):
    name = nameTuple[0]
    if len(name) > 20:
        return u"{}…".format(name[0:20])
    return name


# Map our columns to TSNL's labels, in our chosen order, and provide mapping function
# This should include all possible columns
DEFAULT_COLUMN_SPEC = [
    (Stat.NUM, "NR", ident),
    (Stat.STATE, "", lambda i: mapState(i[0])),
    (Stat.CLASS, "CLS", ident),
    (Stat.TEAM, "TEAM", shorten),
    (Stat.TEAM, "TEAM NAME", shorten),
    (Stat.DRIVER, "NAME", ident),
    (Stat.DRIVER, "DRIVER IN CAR", ident),
    (Stat.DRIVER, "DRIVER", ident),
    (Stat.CAR, "CAR", shorten),
    (Stat.CAR, "BRAND", shorten),
    (Stat.LAPS, "LAPS", ident),
    (Stat.GAP, "GAP", lambda i: parseTime(i[0])),
    (Stat.INT, "DIFF", lambda i: parseTime(i[0])),
    (Stat.S1, "SECT 1", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.S2, "SECT 2", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.S3, "SECT 3", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.S1, "SECT-1", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.S2, "SECT-2", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.S3, "SECT-3", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.LAST_LAP, "LAST", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.BEST_LAP, "BEST", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.PITS, "PIT", ident)
]


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tk", help="timeservice.nl feed ID")
    # Known IDs:
    # Dubai - 17047960b73e48c4a899f43a2459cc20
    # Bathurst 12H - 59225c5480a74b178deaf992976595c3
    # Mugello - 237baff60dfb4291ab20f72319e79aa2

    return parser.parse_args(args)


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)

        self.myArgs = parse_extra_args(config.extra['extra_args'])

        socketURL = getWebSocketURL(self.getTrackID(), getToken())
        factory = WebSocketClientFactory(socketURL)
        factory.protocol = create_protocol(self)
        connectWS(factory)

        self.carState = {}
        self.sessionState = {"flagState": "none"}
        self.timeOffset = None
        self.times = {}

        self.messages = []
        self.yellowFlags = []
        self.raceFlag = "none"

        self.description = ""
        self.columnSpec = map(lambda c: c[0], DEFAULT_COLUMN_SPEC)
        self.carFieldMapping = []

    def getTrackID(self):
        '''
        By default take track ID or alias from commandline args - but
        subclasses can override this method to provide a fixed value.
        '''
        known_tracks = {
            'bathurst': '59225c5480a74b178deaf992976595c3',
            'demo': 'aed5546e3b5e46aeb6ba564f6f72457d',
            'dubai': '17047960b73e48c4a899f43a2459cc20',
            'mugello': '237baff60dfb4291ab20f72319e79aa2',
            'redbullring': '21e603fd091949538a85e836bff214e6'
        }

        if self.myArgs.tk in known_tracks:
            return known_tracks[self.myArgs.tk]

        return self.myArgs.tk

    def getName(self):
        return "timeservice.nl feed"

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return self.columnSpec

    def getPollInterval(self):
        return 1

    def a_r(self, body):
        # clear stats page - ignore
        pass

    def a_u(self, body):
        # best lap history - ignore
        pass

    def r_i(self, body):
        if 'r' in body:
            self.carState = {}
            self.r_c(body['r'])
        if 'l' in body:
            self.r_l(body['l'])

    def r_c(self, body):
        for update in body:
            if update[0] != -1 and update[1] != -1:
                if update[0] not in self.carState:
                    self.carState[update[0]] = {}
                self.carState[update[0]][update[1]] = (update[2], None) if len(update) == 3 else (update[2], update[3])

    def r_d(self, idx):
        if idx == 0:
            self.carState.clear()
            self.analyser.reset()
        elif idx in self.carState:
            self.carState.pop(idx)

    def r_l(self, body):
        if 'h' in body:
            # Dynamically generate column spec and mapping
            availableColumns = map(lambda h: h['c'], body['h'])
            self.carFieldMapping = []
            self.log.info("Discovered columns: {}".format(availableColumns))
            newColumnSpec = []
            for stat, label, mapFunc in DEFAULT_COLUMN_SPEC:
                if stat not in newColumnSpec:
                    # if mapped col exists in availableColumns
                    # and not yet in newColumnSpec, add it to newColumnSpec
                    try:
                        idx = availableColumns.index(label)
                        newColumnSpec.append(stat)
                        self.carFieldMapping.append((idx, mapFunc))
                    except ValueError:
                        self.log.info("Label {} not found in columns, dropping {}".format(label, stat))
            self.columnSpec = newColumnSpec
            self.publishManifest()
            self.carFieldMapping.append((availableColumns.index("POS"), lambda x: int(x[0])))

    def h_h(self, body):
        if "f" in body:
            self.raceFlag = mapFlag(body["f"])
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
        if "c" in body:
            print "Track length: {}".format(body["c"])

    def h_i(self, body):
        self.h_h(body)

    def m_i(self, body):
        # multiple messages
        for msg in body:
            self.m_c(msg)

    def m_c(self, body):
        # race control message
        if 'Id' in body and 't' in body:
            self.messages.append(body['t'])
            if body['t'].startswith("Yellow flag"):
                self.yellowFlags.append(body['Id'])

    def m_d(self, msgId):
        # delete message
        if msgId in self.yellowFlags:
            self.yellowFlags.remove(msgId)

    def s_t(self, serverTime):
        self.timeOffset = serverToRealTime(serverTime) - utcnow()
        self.log.info("Set time offset to {}".format(self.timeOffset))

    def t_p(self, body):
        # track position - ignore
        pass
#         for P in body:
#             J = P[0]
#             carNum = P[1]
#             position = P[2]  # distance from start line in mm (km * 1e6) - might vary by circuit?
#             T = P[3]
#             sector = P[4]  # -1 == pits
#             speed = P[5]  # mm/s (!)
#             inPit = P[6]
#             timestamp = P[7]
#             print P
#             print "{} @ {}km (sector {}) Spd: {} km/h Time: {}".format(carNum, position / 1000000.0, sector, 60 * 60 * speed / 1000000, serverToRealTime(timestamp, self.timeOffset))

    def t_l(self, length):
        print "Track length: {}".format(length)

    def mapCar(self, car):
        result = [mapFunc(car[idx]) for idx, mapFunc in self.carFieldMapping]

        lastIdx = self.getColumnSpec().index(Stat.LAST_LAP)
        bestIdx = self.getColumnSpec().index(Stat.BEST_LAP)

        if len(result[lastIdx]) == 2 and result[lastIdx][1] == "sb" and result[lastIdx][0] == result[bestIdx][0]:
            result[lastIdx] = (result[lastIdx][0], "sb-new")

        return result

    def getRaceState(self):
        session = {}
        if "lt" in self.times and "r" in self.times and "q" in self.times and self.timeOffset:
            if "h" in self.times and self.times["h"]:
                session['timeRemain'] = self.times['r'] / 1000000
            else:
                serverNow = realToServerTime(utcnow() + self.timeOffset)
                elapsed = (serverNow - self.times['q'] + self.times['r'])
                session['timeElapsed'] = elapsed / 1000000
                session['timeRemain'] = (self.times['lt'] - elapsed) / 1000000

        if self.raceFlag == "green" and len(self.yellowFlags) > 0:
            self.log.debug("Overriding flag state {} as {} yellow flags shown".format(self.raceFlag, len(self.yellowFlags)))
            session['flagState'] = "yellow"
        else:
            session['flagState'] = self.raceFlag

        state = {
            "cars": sorted(map(self.mapCar, self.carState.values()), key=lambda c: c[-1]),
            "session": session
        }
        return state

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]

    def getAnalysisModules(self):
        return [
            LaptimeAnalysis,
            PitStopAnalysis,
            StintLength
        ]
