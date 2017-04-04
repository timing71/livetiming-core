# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.analysis.driver import StintLength
from livetiming.analysis.laptimes import LapChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from twisted.logger import Logger

import re
import simplejson
import time
import urllib2


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
        "1": "LM P1",
        "2": "LM GTE Pro",
        "3": "LM P2",
        "4": "LM GTE Am",
        "5": "Garage 56"
    }
    return classMap[rawClass] if rawClass in classMap else "Unknown"


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
        return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def parseSessionTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%H : %M : %S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        if formattedTime.startswith("24"):
            return 86400
        else:
            return formattedTime


def formatTime(seconds):
    m, s = divmod(seconds, 60)
    return "{}:{}".format(int(m), s)


def hackDataFromJSONP(data, var):
    return simplejson.loads(re.search(r'(?:%s = jQuery\.parseJSON\(\')([^\;]+)(?:\'\)\;)' % var, data).group(1).replace("\\\'", "'"))


def findStaticDataURL(start):
    high = start
    trying = high + 1
    while trying < high + 10:
        url = "http://live.fiawec.com/wpphpFichiers/1/live/referentiel_{}.js".format(trying)
        try:
            urllib2.urlopen(url)
            high = trying
        except Exception:
            pass
        trying += 1
    url = "http://live.fiawec.com/wpphpFichiers/1/live/referentiel_{}.js".format(high)
    Logger().info("Found static data URL: {}".format(url))
    return url


class Service(lt_service):
    log = Logger()

    def __init__(self, config):
        lt_service.__init__(self, config)
        self.staticData = self.getStaticData()

    def getName(self):
        return "WEC"

    def getDefaultDescription(self):
        return "World Endurance Championship"

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
            Stat.INT,
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
            "Forecast"
        ]

    def getPollInterval(self):
        return 20

    def getAnalysisModules(self):
        return [
            LapChart,
            EnduranceStopAnalysis,
            StintLength
        ]

    def getStaticData(self):
        Logger().info("Retrieving WEC static data...")
        static_data_url = findStaticDataURL(554)
        feed = urllib2.urlopen(static_data_url)
        raw = feed.read()
        return {
            "tabPays": hackDataFromJSONP(raw, "tabPays"),
            "tabCategories": hackDataFromJSONP(raw, "tabCategories"),
            "tabMarques": hackDataFromJSONP(raw, "tabMarques"),
            "tabVehicules": hackDataFromJSONP(raw, "tabVehicules"),
            "tabTeams": hackDataFromJSONP(raw, "tabTeams"),
            "tabPilotes": hackDataFromJSONP(raw, "tabPilotes"),
            "tabEngages": hackDataFromJSONP(raw, "tabEngages")
        }

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []
        fastLapsPerClass = {}
        rawCarData = raw[0]

        for car in rawCarData.values():
            lastLap = parseTime(car["8"])
            carClass = self.staticData["tabEngages"][car["2"]]["categorie"] if car["2"] in self.staticData["tabEngages"] else -1
            if lastLap > 0 and (carClass not in fastLapsPerClass or fastLapsPerClass[carClass] > lastLap):
                fastLapsPerClass[carClass] = lastLap

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

        for pos in sorted(rawCarData.iterkeys(), key=lambda i: int(i)):
            car = rawCarData[pos]
            engage = self.staticData["tabEngages"][car["2"]] if car["2"] in self.staticData["tabEngages"] else {"categorie": -1, "team": -1, "voiture": -1, "num": car["2"]}
            voiture = self.staticData["tabVehicules"][engage['voiture']] if engage['voiture'] in self.staticData["tabVehicules"] else {"nom": "Unknown", "marque": -1}
            marque = self.staticData["tabMarques"][voiture['marque']] if voiture['marque'] in self.staticData["tabMarques"] else "Unknown"
            driver = self.staticData["tabPilotes"][car["5"]] if car["5"] in self.staticData["tabPilotes"] else {"prenom": "Driver", "nom": car["5"]}
            team = self.staticData["tabTeams"][engage["team"]] if engage["team"] in self.staticData["tabTeams"] else {"nom": "Unknown"}
            classe = engage["categorie"]
            lastLap = parseTime(car["12"])
            bestLap = parseTime(car["8"])

            cars.append([
                engage["num"],
                mapCarState(car["9"]),
                mapClasses(classe),
                team["nom"],
                u"{}, {}".format(driver["nom"].upper(), driver['prenom']),
                u"{} {}".format(marque, voiture["nom"]),
                car["6"],
                car["13"],
                car["4"],  # gap
                car["16"],  # int
                [lastLap, getFlags(classe, lastLap, bestLap)],
                [bestLap, getFlags(classe, bestLap, -1)],
                car["1"],  # ave speed
                car["20"]  # pits
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
                trackData["1"].title()
            ]
        }

        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://live.fiawec.com/wpphpFichiers/1/live/FIAWEC/data.js?tx={}&t={}".format(
            "",
            int(time.time() / 15)
        )
        feed = urllib2.urlopen(feed_url)
        return simplejson.loads(feed.read())