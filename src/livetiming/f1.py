# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.service import MultiLineFetcher, Service as lt_service
from twisted.logger import Logger
import math
import simplejson
import random
import re
import urllib2
import xml.etree.ElementTree as ET
from livetiming.messages import CarPitMessage, FastLapMessage, TimingMessage
from livetiming.racing import FlagStatus


class RaceControlMessage(TimingMessage):
    def _consider(self, oldState, newState):
        if newState["raceControlMessage"] is not None:
            msg = newState["raceControlMessage"]
            return ["Race Control", msg, "raceControl"]


def mapTimeFlag(color):
    timeMap = {
        "P": "sb",
        "G": "pb",
        "Y": "old"
    }
    if color in timeMap:
        return timeMap[color]
    return ""


def renderGapOrLaps(raw):
    if raw != "" and raw[0] == "-":
        laps = -1 * int(raw)
        return "{} lap{}".format(laps, "s" if laps > 1 else "")
    return raw


def parseTyre(tyreChar):
    tyreMap = {
        "H": ("H", "tyre-hard"),
        "M": ("M", "tyre-med"),
        "S": ("S", "tyre-soft"),
        "V": ("SS", "tyre-ssoft"),
        "E": ("US", "tyre-usoft"),
        "I": ("I", "tyre-inter"),
        "W": ("W", "tyre-wet"),
        "U": ("U", "tyre-development"),
    }
    return tyreMap[tyreChar]


def parseFlagState(flagChar):
    flagMap = {
        "C": FlagStatus.CHEQUERED,
        "Y": FlagStatus.YELLOW,
        "V": FlagStatus.VSC,
        "S": FlagStatus.SC,
        "R": FlagStatus.RED
    }
    if flagChar in flagMap:
        return flagMap[flagChar].name.lower()
    return "green"


def getServerConfig():
    serverListXML = urllib2.urlopen("http://www.formula1.com/sp/static/f1/2016/serverlist/svr/serverlist.xml")
    servers = ET.parse(serverListXML)
    race = servers.getroot().attrib['race']
    session = servers.getroot().attrib['session']
    serverIP = random.choice(servers.findall('Server')).get('ip')
    Logger().info("Using server {}".format(serverIP))
    return "http://{}/f1/2016/live/{}/{}/".format(serverIP, race, session)


class Service(lt_service):

    DATA_REGEX = re.compile(r"^(?:SP\._input_\(')([a-z]+)(?:',)(.*)\);$")

    def __init__(self, config):
        lt_service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        server_base_url = getServerConfig()
        self.dataMap = {}
        self.prevRaceControlMessage = ""
        allURL = server_base_url + "all.js"
        allFetcher = MultiLineFetcher(allURL, self.processData, 60)
        allFetcher.start()
        curFetcher = MultiLineFetcher(server_base_url + "cur.js", self.processData, 1)
        curFetcher.start()
        self.processData(urllib2.urlopen(allURL).readlines())
        self.timestampLastUpdated = datetime.now()

    def processData(self, data):
        for dataline in data:
            matches = self.DATA_REGEX.match(dataline)
            if matches:
                self.dataMap[matches.group(1)] = simplejson.loads(matches.group(2))
                if matches.group(1) == "f":
                    self.timestampLastUpdated = datetime.now()

    def getName(self):
        return "Formula 1"

    def getDefaultDescription(self):
        return "Formula 1"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Driver", "text"),
            ("Lap", "num"),
            ("T", "text"),
            ("TS", "text"),
            ("TA", "text"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("S1", "time"),
            ("BS1", "time"),
            ("S2", "time"),
            ("BS2", "time"),
            ("S3", "time"),
            ("BS3", "time"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "num")
        ]

    def getTrackDataSpec(self):
        return [
            "Track Temp",
            "Air Temp",
            "Wind Speed",
            "Direction",
            "Humidity",
            "Pressure",
            "Track",
            "Forecast"
        ]

    def getPollInterval(self):
        return 1

    def getRaceState(self):
        cars = []
        drivers = []
        bestTimes = []
        latestTimes = []
        sq = []
        comms = {}
        extra = []
        flag = None

        for key, val in self.dataMap["init"].iteritems():
            if key != "T" and key != "TY":
                drivers = val["Drivers"]

        for key, val in self.dataMap["b"].iteritems():
            if key != "T" and key != "TY":
                bestTimes = val["DR"]
                flag = val["F"]

        for key, val in self.dataMap["o"].iteritems():
            if key != "T" and key != "TY":
                latestTimes = val["DR"]

        for key, val in self.dataMap["sq"].iteritems():
            if key != "T" and key != "TY":
                sq = val["DR"]

        for key, val in self.dataMap["c"].iteritems():
            if key != "T" and key != "TY":
                comms = val

        for key, val in self.dataMap["x"].iteritems():
            if key != "T" and key != "TY":
                extra = val["DR"]

        free = self.dataMap["f"]["free"]

        denormalised = []

        for idx, driver in enumerate(drivers):
            dnd = {}
            dnd["driver"] = driver
            dnd["timeLine"] = bestTimes[idx]["B"].split(",")
            if "STOP" in bestTimes[idx]:
                dnd["stop"] = bestTimes[idx]["STOP"]
            dnd["latestTimeLine"] = latestTimes[idx]["O"].split(",")
            dnd["sq"] = sq[idx]["G"].split(",")
            dnd["extra"] = extra[idx]
            denormalised.append(dnd)

        fastestLap = min(map(lambda d: float(d["timeLine"][1]) if d["timeLine"][1] != "" else 9999, denormalised))

        for dnd in sorted(denormalised, key=lambda d: int(d["latestTimeLine"][4])):
            driver = dnd["driver"]
            latestTimeLine = dnd["latestTimeLine"]
            timeLine = dnd["timeLine"]
            colorFlags = dnd["latestTimeLine"][2]
            sq = dnd["sq"]

            if "X" in dnd["extra"] and dnd["extra"]["X"].split(",")[9] != "":
                currentTyre = parseTyre(dnd["extra"]["X"].split(",")[9][0])
                currentTyreStats = dnd["extra"]["TI"].split(",")[-4:-1]
            else:
                currentTyre = ""
                currentTyreStats = ("", "", "")

            state = "RUN"
            if "stop" in dnd:
                state = "RET"
            elif latestTimeLine[3][2] == "1" or latestTimeLine[3][2] == "3":
                state = "PIT"

            fastestLapFlag = ""
            if timeLine[1] != "" and fastestLap == float(timeLine[1]):
                fastestLapFlag = "sb-new" if timeLine[1] == latestTimeLine[1] and state == "RUN" else "sb"

            gap = renderGapOrLaps(latestTimeLine[9])
            interval = renderGapOrLaps(latestTimeLine[14])

            if gap == "" and len(cars) > 0 and timeLine[1] != "":
                fasterCarTime = cars[-1][16][0]
                fastestCarTime = cars[0][16][0]
                ourBestTime = float(timeLine[1])
                interval = ourBestTime - fasterCarTime
                gap = ourBestTime - fastestCarTime

            cars.append([
                driver["Num"],
                state,
                driver["FullName"].title(),
                math.floor(float(sq[0])) if sq[0] != "" else 0,
                currentTyre,
                currentTyreStats[1],
                currentTyreStats[2],
                gap,
                interval,
                [latestTimeLine[5], mapTimeFlag(colorFlags[1])],
                [timeLine[4], 'old'],
                [latestTimeLine[6], mapTimeFlag(colorFlags[2])],
                [timeLine[7], 'old'],
                [latestTimeLine[7], mapTimeFlag(colorFlags[3])],
                [timeLine[10], 'old'],
                [float(latestTimeLine[1]), "sb-new" if fastestLapFlag == "sb-new" else mapTimeFlag(colorFlags[0])],
                [float(timeLine[1]), fastestLapFlag] if timeLine[1] != "" else [0.0, ""],
                latestTimeLine[3][0]
            ])

        currentLap = free["L"]
        totalLaps = free["TL"]

        lapsRemain = max(totalLaps - currentLap, 0)

        session = {
            "flagState": parseFlagState(free["FL"] if flag is None else flag),
            "timeElapsed": 0,
            "timeRemain": free["QT"] - (datetime.now() - self.timestampLastUpdated).total_seconds(),
            "trackData": self._getTrackData()
        }

        if "S" in free and free["S"] == "Race":
            session["lapsRemain"] = math.floor(lapsRemain)

        state = {
            "cars": cars,
            "session": session,
            "raceControlMessage": comms["M"] if ("M" in comms and comms["M"] != self.prevRaceControlMessage) else None
        }

        self.prevRaceControlMessage = comms["M"] if "M" in comms else ""

        return state

    def _getTrackData(self):
        for key, val in self.dataMap["sq"].iteritems():
            if key != "T" and key != "TY":
                if "W" in val:
                    w = val["W"].split(",")
                    return [
                        u"{}°C".format(w[0]),
                        u"{}°C".format(w[1]),
                        "{}kph".format(w[3]),
                        u"{}°".format(float(w[6]) - self._getTrackRotationOffset()),
                        "{}%".format(w[4]),
                        "{}mbar".format(w[5]),
                        "Wet" if w[2] == "1" else "Dry",
                        w[7]
                    ]
        return []

    def _getTrackRotationOffset(self):
        return -45  # XXX this is Monaco's hardcoded value

    def getMessageGenerators(self):
        return super(Service, self).getMessageGenerators() + [
            CarPitMessage(lambda c: c[1], lambda c: "Pits", lambda c: c[2]),
            FastLapMessage(lambda c: c[15], lambda c: "Timing", lambda c: c[2]),
            RaceControlMessage()
        ]
