# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from twisted.internet.task import LoopingCall

import simplejson
import urllib2


def createProtocol(series, service):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            service.log.info("Connected to upstream timing source")
            self.factory.resetDelay()

        def onOpen(self):
            self.sendMessage('{H: "streaming", M: "JoinFeeds", A: ["' + series + '", ["data", "weather", "status", "time"]], I: 0}')
            self.sendMessage('{"H":"streaming","M":"GetData2","A":["' + series + '",["data","statsfeed","weatherfeed","sessionfeed","trackfeed","timefeed"]],"I":1}')

        def onMessage(self, payload, isBinary):
            service.onTimingPayload(simplejson.loads(payload.decode('utf8')))
    return ClientProtocol


def getToken():
    tokenData = simplejson.load(urllib2.urlopen("http://gpserieslivetiming.cloudapp.net/streaming/negotiate?clientProtocol=1.5"))
    return (tokenData["ConnectionId"], tokenData["ConnectionToken"])


def getWebSocketURL(token):
    return "ws://gpserieslivetiming.cloudapp.net/streaming/connect?transport=webSockets&clientProtocol=1.5&connectionToken={}&connectionData=%5B%7B%22name%22%3A%22streaming%22%7D%5D&tid=9".format(urllib2.quote(token[1]))


def parseState(rawState):
    if rawState["InPit"] == 1:
        return "PIT"
    elif rawState["PitOut"] == 1:
        return "OUT"
    elif rawState["Retired"] == 1:
        return "RET"
    elif rawState["Stopped"] == 1:
        return "STOP"
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

    flag = "sb" if "OverallFastest" in timeBlock and timeBlock["OverallFastest"] == 1 else "pb" if "PersonalFastest" in timeBlock and timeBlock["PersonalFastest"] == 1 else ""

    return [timeVal, flag]


def parseSessionTime(rawTime):
    try:
        ttime = datetime.strptime(rawTime, "%H:%M:%S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        try:
            ttime = datetime.strptime(rawTime, "%M:%S")
            return (60 * ttime.minute) + ttime.second
        except ValueError:
            return rawTime


def parseFlag(rawFlag):
    flagMap = {
        "1": FlagStatus.GREEN,
        "2": FlagStatus.YELLOW,
        "4": FlagStatus.SC,
        "5": FlagStatus.RED,
        "6": FlagStatus.VSC
    }
    if rawFlag in flagMap:
        return flagMap[rawFlag].name.lower()
    return "none"


class Service(lt_service):
    attribution = ['Formula Motorsport Ltd', 'http://www.fiaformula2.com/']
    auto_poll = False

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)
        socketURL = getWebSocketURL(getToken())
        factory = ReconnectingWebSocketClientFactory(socketURL)
        factory.protocol = self.getClientProtocol()

        connectWS(factory)

        self.carState = []
        self.sessionState = {"flagState": "none"}
        self.timeLeft = 0
        self.clock_running = False
        self.lastTimeUpdate = datetime.utcnow()
        self.sessionFeed = None
        self.trackFeed = None
        self.weatherFeed = {}

        self._timestamps = {}

        self.description = self.getName()

        self._due_publish_state = False

    def start(self):
        def maybePublish():
            if self._due_publish_state:
                self._updateAndPublishRaceState()
                self._due_publish_state = False
        LoopingCall(maybePublish).start(1)

        super(Service, self).start()

    def getClientProtocol(self):
        return createProtocol("F2", self)

    def getName(self):
        return "Formula 2"

    def getDefaultDescription(self):
        return self.description

    def getPollInterval(self):
        return 1

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getTrackDataSpec(self):
        return [
            "Track Temp",
            "Air Temp",
            "Wind Speed",
            "Direction",
            "Humidity",
            "Pressure",
            "Track"
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
                for car in carList:
                    self.carState.append([
                        car["driver"]["RacingNumber"],
                        parseState(car["status"]),
                        car["driver"]["FullName"],
                        car["laps"]["Value"],
                        car["gapP"]["Value"] if "gapP" in car else car["gap"]["Value"] if "gap" in car else "",
                        car["intervalP"]["Value"] if "intervalP" in car else car["interval"]["Value"] if "interval" in car else "",
                        parseTime(car["sectors"][0]),
                        parseTime(car["sectors"][1]),
                        parseTime(car["sectors"][2]),
                        parseTime(car["last"]),
                        parseTime(car["best"]),
                        car["pits"]["Value"],
                        int(car["position"]["Value"])
                    ])

                newDescription = payload["R"]["data"][1]["Session"]
                self._setDescription(newDescription)

            if "sessionfeed" in payload["R"]:
                self.sessionFeed = payload["R"]["sessionfeed"][1]["Value"]
            if "trackfeed" in payload["R"]:
                self.trackFeed = payload["R"]["trackfeed"][1]["Value"]
            if "timefeed" in payload["R"]:
                self.timeLeft = parseSessionTime(payload["R"]["timefeed"][2])
                self.lastTimeUpdate = datetime.utcnow()
            if "weatherfeed" in payload["R"]:
                self.weatherFeed.update(payload["R"]["weatherfeed"][1])
        elif payload:  # is not empty
            print "What is {}?".format(payload)
        self._due_publish_state = True

    def handleTimingMessage(self, message):
        messageType = message["M"]

        if messageType not in self._timestamps or message["A"][0] >= self._timestamps[messageType]:
            if messageType == "datafeed":
                data = message["A"][2]
                if 'lines' in data:
                    for line in data["lines"]:
                        car = [car for car in self.carState if car[0] == line["driver"]["RacingNumber"]][0]
                        if "sectors" in line:
                            for sector in line["sectors"]:
                                car[int(sector["Id"]) + 5] = parseTime(sector)
                        if "laps" in line:
                            car[3] = line["laps"]["Value"]
                        if "status" in line:
                            car[1] = parseState(line["status"])
                            if car[1] == 'PIT' and car[9][1] == 'sb-new':
                                car[9][1] == 'sb'
                        if "last" in line:
                            car[9] = parseTime(line["last"])
                            if car[9][0] == car[10][0] and car[9][1] == 'sb' and car[8][0] != '' and car[1] == 'RUN':  # last == best == sb and just set S3
                                car[9][1] = 'sb-new'
                        if "position" in line:
                            car[-1] = int(line["position"]["Value"])
                        if "gap" in line:
                            car[4] = line["gap"]["Value"]
                        if "interval" in line:
                            car[5] = line["interval"]["Value"]
                        if "gapP" in line:
                            car[4] = line["gapP"]["Value"]
                        if "intervalP" in line:
                            car[5] = line["intervalP"]["Value"]
                        if "pits" in line:
                            car[11] = line["pits"]["Value"]
                if "Session" in data:
                    self._setDescription(data['Session'])
                else:
                    try:
                        if "Session" in message["A"][1]:
                            self._setDescription(message["A"][1]["Session"])
                    except TypeError:
                        pass

            if messageType == "statsfeed":
                data = message["A"][1]
                if 'lines' in data:
                    for line in data["lines"]:
                        car = [car for car in self.carState if car[0] == line["driver"]["RacingNumber"]][0]
                        if "PersonalBestLapTime" in line and line["PersonalBestLapTime"] is not None:
                            car[10] = parseTime(line["PersonalBestLapTime"])
                        if "Position" in line:
                            car[-1] = int(line["Position"])

            if messageType == "timefeed":
                self.clock_running = message['A'][1]
                self.timeLeft = parseSessionTime(message["A"][2])
                self.lastTimeUpdate = datetime.utcnow()

            if messageType == "sessionfeed":
                self.sessionFeed = message["A"][1]["Value"]

            if messageType == "trackfeed":
                self.trackFeed = message["A"][1]["Value"]

            if messageType == "weatherfeed":
                self.weatherFeed[message["A"][1]] = message["A"][2]

            self._timestamps[messageType] = message['A'][0]

    def _setDescription(self, description):
        if description != self.description:
            self.description = description
            self.publishManifest()

    def getRaceState(self):
        if self.clock_running:
            self.sessionState["timeRemain"] = self.timeLeft - (datetime.utcnow() - self.lastTimeUpdate).total_seconds()
        else:
            self.sessionState['timeRemain'] = self.timeLeft

        if self.sessionFeed == "Finished" or self.sessionFeed == "Finalised":
            self.sessionState["flagState"] = FlagStatus.CHEQUERED.name.lower()  # Override trackfeed value
        elif self.sessionFeed == 'Aborted':
            self.sessionState["flagState"] = FlagStatus.RED.name.lower()
        else:
            self.sessionState["flagState"] = parseFlag(self.trackFeed)

        self.sessionState["trackData"] = self._getTrackData()

        return {"cars": sorted(self.carState, key=lambda car: car[-1]), "session": self.sessionState}

    def _getTrackData(self):

        def maybeValue(key, formatString):
            return formatString.format(self.weatherFeed[key]) if key in self.weatherFeed else None

        return [
            maybeValue('tracktemp', u"{}°C"),
            maybeValue('airtemp', u"{}°C"),
            maybeValue('windspeed', "{}m/s"),
            maybeValue('winddir', u"{}°"),
            maybeValue('humidity', "{}%"),
            maybeValue('pressure', "{}mBar"),
            'Wet' if self.weatherFeed.get('rainfall', 0) == 1 else 'Dry'
        ]
