# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.analysis.driver import StintLength
from livetiming.analysis.lapchart import LapChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, JSONFetcher
from twisted.internet import reactor

import time
import re
import simplejson
import urllib2


def hackDataFromJSONP(data, var):
    return simplejson.loads(re.search(r'(?:%s = )([^\;]+)(?:\;)' % var, data).group(1).replace("\\\'", "'"))


def mapFlagStates(rawState):
    flagMap = {
        1: FlagStatus.YELLOW,
        2: FlagStatus.GREEN,
        3: FlagStatus.RED,
        4: FlagStatus.CHEQUERED,
        5: FlagStatus.YELLOW,
        6: FlagStatus.FCY
    }
    if rawState in flagMap:
        return flagMap[rawState].name.lower()
    return "none"


def mapCarState(rawState):
    stateMap = {
        1: "RET",
        2: "RUN",
        3: "OUT",
        4: "PIT"
    }
    if rawState in stateMap:
        return stateMap[rawState]
    return "RUN"


def mapClasses(rawClass):
    classMap = {
        3: "LMP2",
        6: "LMP3",
        8: "GTC",
        10: "LMGTE",
        16: "GT3"
    }
    return classMap[rawClass] if rawClass in classMap else rawClass


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%S.%f")
        return ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


SESSION_TIME_REGEX = re.compile("(?P<hours>[0-9]{2}) : (?P<minutes>[0-9]{2}) : (?P<seconds>[0-9]{2})")


def parseSessionTime(formattedTime):
    m = SESSION_TIME_REGEX.match(formattedTime)
    if m:
        return (3600 * int(m.group('hours'))) + (60 * int(m.group('minutes'))) + int(m.group('seconds'))
    try:
        ttime = datetime.strptime(formattedTime, "%H : %M : %S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        if formattedTime.startswith("24"):
            return 86400
        else:
            return formattedTime


class Service(lt_service):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.description = self.getName()
        self.staticData = None
        self.rawData = None
        self._last_update = None
        self.setStaticData()

        def feedUrl():
            return self.getRawFeedDataUrl().format(
                "",
                int(time.time() / 15)
            )

        fetcher = JSONFetcher(feedUrl, self.setRawData, 15)
        fetcher.start()

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.TEAM,
            Stat.DRIVER,
            Stat.CAR,
            Stat.TYRE,
            Stat.LAPS,
            Stat.GAP,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.SPEED,
            Stat.PITS
        ]

    def getTrackDataSpec(self):
        return [
            "Track Temp",
            "Air Temp",
            "Humidity",
            "Wind Speed",
            "Wind Direction",
            "Weather",
            "Last updated"
        ]

    def getPollInterval(self):
        return None

    def getAnalysisModules(self):
        return [
            LapChart,
            EnduranceStopAnalysis,
            StintLength
        ]

    def setStaticData(self):
        self.log.info("Retrieving static data...")
        feed = urllib2.urlopen(self.getStaticDataUrl())
        raw = feed.read()
        if re.search("No race actually", raw):
            self.log.warn("No static data available. Has the session started yet?")
            reactor.callLater(30, self.setStaticData)
        else:
            description = re.search("<h1 class=\"live_title\">Live on (?P<desc>[^<]+)<", raw)
            if description:
                new_description = description.group("desc").replace("/", "-").decode('utf-8')
                if self.description != new_description:
                    self.description = new_description
                    self.log.info(u"Setting description: {desc}", desc=self.description)
                    self.publishManifest()

            self.staticData = {
                "tabPays": hackDataFromJSONP(raw, "tabPays"),
                "tabCategories": hackDataFromJSONP(raw, "tabCategories"),
                "tabMarques": hackDataFromJSONP(raw, "tabMarques"),
                "tabVehicules": hackDataFromJSONP(raw, "tabVehicules"),
                "tabTeams": hackDataFromJSONP(raw, "tabTeams"),
                "tabPilotes": hackDataFromJSONP(raw, "tabPilotes"),
                "tabEngages": hackDataFromJSONP(raw, "tabEngages")
            }
            reactor.callLater(120, self.setStaticData)  # Refresh the static data every two minutes

    def setRawData(self, data):
        self.rawData = data
        self._last_update = datetime.utcnow()
        self._updateAndPublishRaceState()

    def getRaceState(self):
        if self.staticData is None or self.rawData is None:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0,
                    "timeRemain": -1
                }
            }

        raw = self.rawData
        cars = []
        fastLapsPerClass = {}
        rawCarData = raw[0]

        try:
            for car in rawCarData.values():
                lastLap = parseTime(car["8"])
                carClass = self.staticData["tabEngages"][car["2"]]["categorie"] if car["2"] in self.staticData["tabEngages"] else -1
                if lastLap > 0 and (carClass not in fastLapsPerClass or fastLapsPerClass[carClass] > lastLap):
                    fastLapsPerClass[carClass] = lastLap
        except AttributeError:
            pass  # can happen if rawCarData is empty - server returns list rather than empty object in that case

        def getFlags(carClass, last, best):
            if carClass in fastLapsPerClass and last == fastLapsPerClass[carClass]:
                if last == best:
                    return "sb-new"
                return "sb"
            elif last == best and last > 0:
                return "pb"
            elif best > 0 and last > best * 1.6:
                return "slow"
            return ""

        try:
            carKeys = rawCarData.iterkeys()
        except AttributeError:  # can happen if rawCarData is empty - server returns list rather than empty object in that case
            carKeys = []

        for pos in sorted(carKeys, key=lambda i: int(i)):
            car = rawCarData[pos]
            engage = self.staticData["tabEngages"].get(car["2"], {"categorie": "", "team": -1, "voiture": -1, "num": car["2"]})
            voiture = self.staticData["tabVehicules"].get(str(engage['voiture']), {"nom": "", "marque": -1})
            marque = self.staticData["tabMarques"].get(str(voiture['marque']), "")
            driver = self.staticData["tabPilotes"].get(car["5"], {"prenom": "Driver", "nom": car["5"]})
            team = self.staticData["tabTeams"].get(str(engage["team"]), {"nom": "Unknown"})
            classe = engage["categorie"]
            lastLap = parseTime(car["12"])
            bestLap = parseTime(car["8"])

            cars.append([
                engage["num"],
                mapCarState(car["9"]),
                mapClasses(classe),
                team["nom"],
                u"{}, {}".format(driver["nom"].upper(), driver['prenom']),
                u"{} {}".format(marque, voiture["nom"]).strip(),
                car["6"],
                car["13"],
                car["4"],  # gap
                [lastLap, getFlags(classe, lastLap, bestLap)] if lastLap > 0 else ['', ''],
                [bestLap, getFlags(classe, bestLap, -1)] if bestLap > 0 else ['', ''],
                car["1"],  # ave speed
                car["16"]  # pits
            ])

        course = raw[1]

        trackData = course["11"][0]

        state = {
            "flagState": FlagStatus.SC.name.lower() if course["9"] == "1" else mapFlagStates(course["6"]),
            "timeElapsed": parseSessionTime(course["4"]),
            "timeRemain": 0 if "7" not in course or course["7"][0] == "-" else parseSessionTime(course["7"]),
            "trackData": [
                u"{}°C".format(trackData["6"]),
                u"{}°C".format(trackData["3"]),
                "{}%".format(trackData["2"]),
                "{}kph".format(trackData["8"]),
                u"{}°".format(trackData["0"]),
                trackData["1"].replace("_", " ").title(),
                self._last_update.strftime("%H:%M:%S UTC") if self._last_update else "-"
            ]
        }

        return {"cars": cars, "session": state}
