# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import WebSocketClientProtocol, connectWS
from datetime import datetime
from livetiming.analysis.laptimes import LaptimeChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.analysis.driver import StintLength
from livetiming.analysis.session import Session
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from lzstring import LZString
from twisted.internet.defer import Deferred

import argparse
import simplejson
import time
import urllib2
import re


def create_protocol(service):
    class TimeserviceNLClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            service.log.info("Connected to TSNL")
            self.factory.resetDelay()

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
            else:
                service.log.warn("Unknown message {msgType}: {msgBody}", msgType=msgType, msgBody=body)

        def onClose(self, wasClean, code, reason):
            service.log.info("Closed connection to TSNL")
    return TimeserviceNLClientProtocol


def mapTimeFlags(flag):
    if flag == "65280":
        return 'pb'
    if flag == "16736511":
        return 'sb'
    if flag == "6579455":
        return "joker"
    if flag == "4210943" or flag == "255":
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


def nonnegative(val):
    try:
        return max(val[0], 0)
    except ValueError:
        return val


TSNL_LAP_IN_GAP_REGEX = re.compile("-- ([0-9]+) laps?")


def parse_gap(val):
    laps = TSNL_LAP_IN_GAP_REGEX.match(val[0])
    if laps:
        lap = int(laps.group(1))
        return "({} lap{})".format(lap, "" if lap == 1 else "s")
    return parseTime(val[0])


def map_sector(sector):
    if len(sector) == 2:
        return (parseTime(sector[0]), mapTimeFlags(sector[1]))
    return ('', '')


# Map our columns to TSNL's labels, in our chosen order, and provide mapping function
# This should include all possible columns
DEFAULT_COLUMN_SPEC = [
    (Stat.NUM, "NR", ident),
    (Stat.NUM, "NBR", ident),
    (Stat.NUM, "NR.", ident),
    (Stat.STATE, "", lambda i: mapState(i[0])),
    (Stat.STATE, "M", lambda i: mapState(i[0])),
    (Stat.CLASS, "CLS", ident),
    (Stat.TEAM, "TEAM", shorten),
    (Stat.TEAM, "TEAM NAME", shorten),
    (Stat.DRIVER, "DRIVER IN CAR", ident),
    (Stat.DRIVER, "NAME", ident),
    (Stat.DRIVER, "DRIVER", ident),
    (Stat.CAR, "CAR", shorten),
    (Stat.CAR, "BRAND", shorten),
    (Stat.CAR, "VEHICLE", shorten),
    (Stat.LAPS, "LAPS", nonnegative),
    (Stat.GAP, "GAP", parse_gap),
    (Stat.INT, "DIFF", lambda i: parseTime(i[0])),
    (Stat.S1, "SECT 1", map_sector),
    (Stat.S1, "SECT.1", map_sector),
    (Stat.S1, "SECT-1", map_sector),
    (Stat.S2, "SECT 2", map_sector),
    (Stat.S2, "SECT.2", map_sector),
    (Stat.S2, "SECT-2", map_sector),
    (Stat.S3, "SECT 3", map_sector),
    (Stat.S3, "SECT.3", map_sector),
    (Stat.S3, "SECT-3", map_sector),
    (Stat.S4, "SECT 4", map_sector),
    (Stat.S4, "SECT.4", map_sector),
    (Stat.S4, "SECT-4", map_sector),
    (Stat.S5, "SECT 5", map_sector),
    (Stat.S5, "SECT.5", map_sector),
    (Stat.S5, "SECT-5", map_sector),
    (Stat.LAST_LAP, "LAST", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.LAST_LAP, "LAST TIME", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.LAST_LAP, "LAST", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.BEST_LAP, "BEST", lambda i: (parseTime(i[0]), mapTimeFlags(i[1]))),
    (Stat.PITS, "PIT", ident)
]


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tk", help="timeservice.nl feed ID")
    # @see Service#getTrackID()

    return parser.parse_args(args)


TID_REGEX = re.compile("^[0-9a-z]{32}$")


class Service(lt_service):
    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)

        self.myArgs = parse_extra_args(extra_args)

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

        tidder = self.getTrackID()
        tidder.addCallback(self._tsnl_connect)

    def _tsnl_connect(self, tid):
        self.log.info("TID: {tid}", tid=tid)
        socketURL = self.getWebSocketURL(tid, self.getToken())
        self.log.info("Websocket URL: {url}", url=socketURL)
        factory = ReconnectingWebSocketClientFactory(socketURL)
        factory.protocol = create_protocol(self)
        connectWS(factory)

    def getToken(self):
        tokenData = simplejson.load(urllib2.urlopen("https://{}/lt/negotiate?clientProtocol=1.5".format(self.getHost())))
        return (tokenData["ConnectionId"], tokenData["ConnectionToken"])

    def getWebSocketURL(self, tk, token):
        return "wss://{}/lt/connect?transport=webSockets&clientProtocol=1.5&_tk={}&_gr=w&connectionToken={}&tid=8".format(self.getHost(), tk, urllib2.quote(token[1]))

    def getHost(self):
        return "livetiming.getraceresults.com"

    def getTrackID(self):
        '''
        By default take track ID or alias from commandline args - but
        subclasses can override this method to provide a fixed value.
        '''
        if TID_REGEX.match(self.myArgs.tk):
            d = Deferred()
            d.callback(self.myArgs.tk)
            return d
        else:
            return self._trackIDFromServiceName(self.myArgs.tk)

    def _trackIDFromServiceName(self, service_name):
        d = Deferred()
        tid_matcher = re.compile("(?:new liveTiming.LiveTimingApp\()(?P<service_data>[^;]+)\);")
        print "Searching for tid for service '{service_name}'".format(service_name=service_name)
        while not d.called:
            tsnl = urllib2.urlopen("https://{}/{}".format(self.getHost(), service_name)).read()

            matches = tid_matcher.search(tsnl)
            if matches:
                svc_data = simplejson.loads(matches.group('service_data'))
                self.log.info("Found TSNL service data: {service_data}", service_data=svc_data)
                d.callback(svc_data['tid'])
                break
            else:
                print "No tid found, trying again in 30 seconds."
                time.sleep(30)
        return d

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
            availableColumns = map(lambda h: h['c'].upper(), body['h'])
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
            self.log.debug("Track length: {}".format(body["c"]))

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
        self.log.debug("Track length: {}".format(length))

    def mapCar(self, car):
        result = [mapFunc(car[idx] if idx < len(car) else '') for idx, mapFunc in self.carFieldMapping]

        colSpec = self.getColumnSpec()
        if Stat.LAST_LAP in colSpec and Stat.BEST_LAP in colSpec:
            lastIdx = colSpec.index(Stat.LAST_LAP)
            bestIdx = colSpec.index(Stat.BEST_LAP)

            stateIdx = colSpec.index(Stat.STATE)
            s3Idx = colSpec.index(Stat.S3) if Stat.S3 in colSpec else None

            if len(result[lastIdx]) == 2 and result[lastIdx][1] == "sb" and result[lastIdx][0] == result[bestIdx][0]:
                if result[stateIdx] == "RUN" and (s3Idx is None or result[s3Idx][0] > 0):  # Not if in pits or have completed next lap S1
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
            Session,
            LaptimeChart,
            EnduranceStopAnalysis,
            StintLength
        ]
