# -*- coding: utf-8 -*-
from livetiming.racing import FlagStatus, Stat
from livetiming.service.wec import mapCarState, mapFlagStates, parseSessionTime, parseTime, Service as WEC
from twisted.logger import Logger

import time
import re
import simplejson
import urllib2


def hackDataFromJSONP(data, var):
    return simplejson.loads(re.search(r'(?:%s = )([^\;]+)(?:\;)' % var, data).group(1).replace("\\\'", "'"))


def mapClasses(rawClass):
    classMap = {
        3: "LM P2",
        6: "LM P3",
        8: "GTC",
        10: "LM GTE",
        16: "GT3"
    }
    return classMap[rawClass] if rawClass in classMap else rawClass


class Service(WEC):
    def __init__(self, args, extra_args):
        WEC.__init__(self, args, extra_args)

    def getDefaultDescription(self):
        return self.getName()

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

    def getStaticData(self):
        Logger().info("Retrieving static data...")
        feed = urllib2.urlopen(self.getStaticDataUrl())
        raw = feed.read()
        if re.search("No race actually", raw):
            raise Exception("No static data available. Has the session started yet?")
        return {
            "tabPays": hackDataFromJSONP(raw, "tabPays"),
            "tabCategories": hackDataFromJSONP(raw, "tabCategories"),
            "tabMarques": hackDataFromJSONP(raw, "tabMarques"),
            "tabVehicules": hackDataFromJSONP(raw, "tabVehicules"),
            "tabTeams": hackDataFromJSONP(raw, "tabTeams"),
            "tabPilotes": hackDataFromJSONP(raw, "tabPilotes"),
            "tabEngages": hackDataFromJSONP(raw, "tabEngages")
        }

    def getRawFeedData(self):
        feed_url = self.getRawFeedDataUrl().format(
            "",
            int(time.time() / 15)
        )
        feed = urllib2.urlopen(feed_url)
        return simplejson.loads(feed.read())

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
            voiture = self.staticData["tabVehicules"][str(engage['voiture'])] if str(engage['voiture']) in self.staticData["tabVehicules"] else {"nom": "Unknown", "marque": -1}
            marque = self.staticData["tabMarques"][str(voiture['marque'])] if str(voiture['marque']) in self.staticData["tabMarques"] else "Unknown"
            driver = self.staticData["tabPilotes"][car["5"]] if car["5"] in self.staticData["tabPilotes"] else {"prenom": "Driver", "nom": car["5"]}
            team = self.staticData["tabTeams"][str(engage["team"])] if str(engage["team"]) in self.staticData["tabTeams"] else {"nom": "Unknown"}
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
                [lastLap, getFlags(classe, lastLap, bestLap)],
                [bestLap, getFlags(classe, bestLap, -1)],
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
                trackData["1"].title()
            ]
        }

        return {"cars": cars, "session": state}