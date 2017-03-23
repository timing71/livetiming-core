# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.service import MultiLineFetcher, Service as lt_service
from twisted.logger import Logger
from twisted.internet import reactor
import math
import simplejson
import time
import random
import re
import urllib2
import xml.etree.ElementTree as ET
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.analysis.laptimes import LapChart


_F1_SERVICE_YEAR = 2017


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
        "U": ("U", "tyre-development")
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


class Service(lt_service):

    DATA_REGEX = re.compile(r"^(?:SP\._input_\(')([a-z]+)(?:',)(.*)\);$")
    log = Logger()

    def __init__(self, config):
        lt_service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        self.dataMap = {}
        self.prevRaceControlMessage = None
        self.messages = []
        self.hasSession = False
        self.serverTimestamp = 0
        self.configure()

    def configure(self):
        serverListXML = urllib2.urlopen("http://www.formula1.com/sp/static/f1/{}/serverlist/svr/serverlist.xml".format(_F1_SERVICE_YEAR))
        servers = ET.parse(serverListXML)
        serversRoot = servers.getroot()

        race = serversRoot.attrib.get("race", "")
        session = serversRoot.attrib.get("session", "")
        if race != "" and session != "":
            self.hasSession = True

            serverIP = random.choice(servers.findall('Server')).get('ip')
            self.log.info("Using server {}".format(serverIP))

            server_base_url = "http://{}/f1/{}/live/{}/{}/".format(serverIP, _F1_SERVICE_YEAR, race, session)

            allURL = server_base_url + "all.js"

            allFetcher = MultiLineFetcher(allURL, self.processData, 60)
            allFetcher.start()

            def getCurURL():
                return "{}cur.js?{}".format(server_base_url, self.serverTimestamp if self.serverTimestamp > 0 else "")

            curFetcher = MultiLineFetcher(getCurURL, self.processData, 1)
            curFetcher.start()

            self.processData(urllib2.urlopen(allURL).readlines())
            self.timestampLastUpdated = datetime.now()
            return
        self.log.info("No live session found, checking again in 30 seconds.")
        reactor.callLater(30, self.configure)

    def processData(self, data):
        for dataline in data:
            matches = self.DATA_REGEX.match(dataline)
            if matches:
                content = simplejson.loads(matches.group(2))
                self.dataMap[matches.group(1)] = content
                if "T" in content:
                    self.serverTimestamp = max(self.serverTimestamp, content["T"] / 1000000)
                if matches.group(1) == "f":
                    self.timestampLastUpdated = datetime.now()

    def getName(self):
        return "Formula 1"

    def getDefaultDescription(self):
        if "f" in self.dataMap:
            if "free" in self.dataMap["f"]:
                free = self.dataMap["f"]["free"]

                sessionName = {
                    'Practice1': "Free Practice 1",
                    'Practice2': "Free Practice 2",
                    'Practice3': "Free Practice 3",
                    'Qualifying': "Qualifying",
                    'Race': "Race"
                }

                return "{} - {}".format(
                    free.get("R", "Formula 1").title(),
                    sessionName[free.get("S", "")]
                )
        return "Formula 1"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.TYRE,
            Stat.TYRE_STINT,
            Stat.TYRE_AGE,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.BS1,
            Stat.S2,
            Stat.BS2,
            Stat.S3,
            Stat.BS3,
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

    def getPollInterval(self):
        return 1

    def getAnalysisModules(self):
        return [
            LapChart
        ]

    def _getData(self, key, subkey=None):
        if key in self.dataMap:
            for key, val in self.dataMap[key].iteritems():
                if key != "T" and key != "TY":
                    if subkey is not None:
                        if subkey in val:
                            return val[subkey]
                        return None
                    return val
        return None

    def getRaceState(self):
        if not self.hasSession:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0,
                    "timeRemain": -1
                }
            }

        cars = []
        drivers = []
        bestTimes = []
        flag = None

        init = self._getData("init")
        if init:
            drivers = init["Drivers"]
            startTime = init.get("ST", None)

        currentTime = self._getData("cpd", "CT")
        if currentTime is None:
            currentTime = time.time() * 1000

        b = self._getData("b")
        if b:
            bestTimes = b["DR"]
            flag = b["F"]

        latestTimes = self._getData("o", "DR")

        sq = self._getData("sq", "DR")

        comms = self._getData("c")

        extra = self._getData("x", "DR")

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
            "timeElapsed": (currentTime - startTime) / 1000 if startTime else 0,
            "timeRemain": free["QT"] - (datetime.now() - self.timestampLastUpdated).total_seconds(),
            "trackData": self._getTrackData()
        }

        if "S" in free and free["S"] == "Race":
            session["lapsRemain"] = math.floor(lapsRemain)

        state = {
            "cars": cars,
            "session": session,
        }

        if "M" in comms and comms["M"] != self.prevRaceControlMessage:
            self.messages.append(comms["M"])
            self.prevRaceControlMessage = comms["M"]

        return state

    def _getTrackData(self):
        W = self._getData("sq", "W")
        if W:
            w = W.split(",")
            return [
                u"{}°C".format(w[0]),
                u"{}°C".format(w[1]),
                "{} kph".format(w[3]),
                u"{}°".format(float(w[6]) - self._getTrackRotationOffset()),
                "{}%".format(w[4]),
                "{} mbar".format(w[5]),
                "Wet" if w[2] == "1" else "Dry"
            ]
        return []

    def _getTrackRotationOffset(self):
        return -45  # XXX this is Monaco's hardcoded value

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]
