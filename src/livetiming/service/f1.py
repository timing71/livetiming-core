# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import MultiLineFetcher, Service as lt_service
from twisted.logger import Logger
from twisted.internet import reactor
from requests.sessions import Session
from signalr import Connection
from threading import Thread

import math
import simplejson
import time
import random
import re
import urllib2
import xml.etree.ElementTree as ET


class F1Client(Thread):
    def __init__(self, handler):
        Thread.__init__(self)
        self.handler = handler
        self.log = handler.log
        self.host = "livetiming.formula1.com"
        self.daemon = True

    def run(self):
        with Session() as session:
            connection = Connection("https://{}/signalr/".format(self.host), session)
            hub = connection.register_hub('streaming')

            def print_error(error):
                print('error: ', error)

            def delegate(method, data):
                handler_method = "on_{}".format(method.lower())
                if hasattr(self.handler, handler_method) and callable(getattr(self.handler, handler_method)):
                    self.log.debug("Received {method}: {data}", method=method, data=data)
                    getattr(self.handler, handler_method)(data)
                else:
                    self.log.info("Unhandled message {method}: {data}", method=handler_method, data=data)

            def handle(**kwargs):
                if 'M' in kwargs:
                    for msg in kwargs['M']:
                        delegate(msg['M'], msg['A'])
                if 'R' in kwargs:
                    delegate('feed', ['SPFeed', kwargs['R']['SPFeed']])

            connection.error += print_error
            connection.received += handle

            with connection:
                print "Connection happened"
                hub.server.invoke('Subscribe', ['SPFeed', 'ExtrapolatedClock'])
                connection.wait(None)

_F1_SERVICE_YEAR = 2018


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
        "D": ("SH", "tyre-shard"),
        "H": ("H", "tyre-hard"),
        "M": ("M", "tyre-med"),
        "S": ("S", "tyre-soft"),
        "V": ("SS", "tyre-ssoft"),
        "E": ("US", "tyre-usoft"),
        "F": ("HS", "tyre-hsoft"),
        "I": ("I", "tyre-inter"),
        "W": ("W", "tyre-wet"),
        "U": ("U", "tyre-development")
    }
    return tyreMap.get(tyreChar, '?')


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


SESSION_NAME_MAP = {
    'Practice1': "Free Practice 1",
    'Practice2': "Free Practice 2",
    'Practice3': "Free Practice 3",
    'Qualifying': "Qualifying",
    'Race': "Race"
}


def parse_time(formattedTime):
    if formattedTime == "" or formattedTime is None:
        return 0
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            try:
                ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
                return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
            except ValueError:
                return formattedTime


class Service(lt_service):
    attribution = ['FOWC', 'https://www.formula1.com/']

    DATA_REGEX = re.compile(r"^(?:SP\._input_\(')([a-z]+)(?:',)(.*)\);$")
    log = Logger()

    def __init__(self, args, extra_args):
        args.hidden = True  # Always hide F1 due to C&D from FOM
        lt_service.__init__(self, args, extra_args)
        self.carsState = []
        self.sessionState = {}
        self.dataMap = {}
        self.prevRaceControlMessage = None
        self.messages = []
        self.hasSession = False
        self.serverTimestamp = 0
        self.timestampLastUpdated = datetime.now()
        self.dataLastUpdated = datetime.now()

        self._description = 'Formula 1'

        client = F1Client(self)
        client.start()

    def on_feed(self, payload):
        data = payload[1]
        for key, val in data.iteritems():
            if key in self.dataMap:
                self.dataMap[key].update(val)
            else:
                self.dataMap[key] = val
            if key == 'free':
                new_desc = '{} - {}'.format(
                    val['data']['R'],
                    val['data']['S']
                )

                if new_desc != self._description:
                    self._description = new_desc
                    self.publishManifest()
            try:
                if "T" in val:
                    self.serverTimestamp = max(self.serverTimestamp, val["T"] / 1000000)
            except TypeError:
                # not an iterable val
                pass
        self.dataLastUpdated = datetime.now()

    def getName(self):
        return "Formula 1"

    def getDefaultDescription(self):
        return self._description

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
            "Track",
            "Updated"
        ]

    def getPollInterval(self):
        return 1

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
        if 'free' not in self.dataMap:
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

        b = self._getData("best")
        if b:
            bestTimes = b["DR"]
            flag = b["F"]

        latestTimes = self._getData("opt", "DR")

        sq = self._getData("sq", "DR")

        comms = self._getData("commentary")

        extra = self._getData("xtra", "DR")

        free = self._getData('free')

        denormalised = []

        for idx, driver in enumerate(drivers):
            dnd = {}
            dnd["driver"] = driver
            dnd["timeLine"] = bestTimes[idx]["B"]
            if "STOP" in bestTimes[idx]:
                dnd["stop"] = bestTimes[idx]["STOP"]
            dnd["latestTimeLine"] = latestTimes[idx]["O"]
            dnd["sq"] = sq[idx]["G"]
            dnd["extra"] = extra[idx]
            denormalised.append(dnd)

        fastestLap = min(map(lambda d: parse_time(d["timeLine"][1]) if d["timeLine"][1] != "" else 9999, denormalised))

        for dnd in sorted(denormalised, key=lambda d: int(d["latestTimeLine"][4])):
            driver = dnd["driver"]
            latestTimeLine = dnd["latestTimeLine"]
            timeLine = dnd["timeLine"]
            colorFlags = dnd["latestTimeLine"][2]
            sq = dnd["sq"]

            if "X" in dnd["extra"] and dnd["extra"]["X"][9] != "":
                currentTyre = parseTyre(dnd["extra"]["X"][9][0])
                currentTyreStats = dnd["extra"]["TI"][-4:-1]
            else:
                currentTyre = ""
                currentTyreStats = ("", "", "")

            state = "RUN"
            if latestTimeLine[3][2] == "1":
                state = "PIT"
            elif latestTimeLine[3][2] == "2":
                state = "OUT"
            elif latestTimeLine[3][2] == "3":
                state = "STOP"

            fastestLapFlag = ""
            if timeLine[1] != "" and fastestLap == parse_time(timeLine[1]):
                fastestLapFlag = "sb-new" if timeLine[1] == latestTimeLine[1] and state == "RUN" else "sb"

            gap = renderGapOrLaps(latestTimeLine[9])
            interval = renderGapOrLaps(latestTimeLine[14])

            if gap == "" and len(cars) > 0 and timeLine[1] != "":
                fasterCarTime = cars[-1][16][0] or 0
                fastestCarTime = cars[0][16][0] or 0
                ourBestTime = float(timeLine[1])
                interval = ourBestTime - fasterCarTime
                gap = ourBestTime - fastestCarTime

            last_lap = parse_time(latestTimeLine[1])

            cars.append([
                driver["Num"],
                state,
                driver["FullName"].title(),
                math.floor(float(sq[0])) if sq[0] != "" else 0,
                currentTyre,
                currentTyreStats[1] if len(currentTyreStats) > 1 else '?',
                currentTyreStats[2] if len(currentTyreStats) > 2 else '?',
                gap,
                interval,
                [latestTimeLine[5], mapTimeFlag(colorFlags[1])],
                [timeLine[4], 'old'],
                [latestTimeLine[6], mapTimeFlag(colorFlags[2])],
                [timeLine[7], 'old'],
                [latestTimeLine[7], mapTimeFlag(colorFlags[3])],
                [timeLine[10], 'old'],
                [last_lap if last_lap > 0 else '', "sb-new" if fastestLapFlag == "sb-new" else mapTimeFlag(colorFlags[0])],
                [parse_time(timeLine[1]), fastestLapFlag] if timeLine[1] != "" else ['', ''],
                latestTimeLine[3][0]
            ])

        currentLap = free["L"]
        totalLaps = free["TL"]

        lapsRemain = max(totalLaps - currentLap + 1, 0)

        session = {
            "flagState": parseFlagState(free["FL"] if flag is None else flag),
            "timeElapsed": (currentTime - startTime) / 1000 if startTime else 0,
            "timeRemain": free.get("QT", 0) - (datetime.now() - self.timestampLastUpdated).total_seconds(),
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
            w = W
            return [
                u"{}°C".format(w[0]),
                u"{}°C".format(w[1]),
                "{}m/s".format(w[3]),
                u"{}°".format(float(w[6])),
                "{}%".format(w[4]),
                "{} mbar".format(w[5]),
                "Wet" if w[2] == "1" else "Dry",
                self.dataLastUpdated.strftime("%H:%M:%S")
            ]
        return []

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]
