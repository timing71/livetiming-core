from livetiming.service import Service
import urllib2
import re
import simplejson
import time
from datetime import datetime
from twisted.logger import Logger
from os import environ
from autobahn.twisted.wamp import ApplicationRunner
from livetiming.messaging import Realm
from livetiming.racing import FlagStatus


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
        "4": "LM GTE Am"
    }
    return classMap[rawClass]


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    ttime = datetime.strptime(formattedTime, "%M:%S.%f")
    return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def parseSessionTime(formattedTime):
    ttime = datetime.strptime(formattedTime, "%H : %M : %S")
    return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second


def hackDataFromJSONP(data, var):
    return simplejson.loads(re.search(r'(?:%s = jQuery\.parseJSON\(\')([^\;]+)(?:\'\)\;)' % var, data).group(1))


def getStaticData():
    Logger().info("Retrieving WEC static data...")
    static_data_url = "http://live.fiawec.com/wpphpFichiers/1/live/referentiel_472.js"
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


class WEC(Service):
    log = Logger()

    def __init__(self, config):
        Service.__init__(self, config)
        self.staticData = getStaticData()

    def getName(self):
        return "WEC"

    def getDescription(self):
        return "World Endurance Championship"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Class", "class"),
            ("Team", "text"),
            ("Driver", "text"),
            ("Car", "text"),
            ("T", "text"),
            ("Laps", "numeric"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("Last", "time"),
            ("Best", "time"),
            ("Spd", "numeric"),
            ("Pits", "numeric")
        ]

    def getPollInterval(self):
        return 20

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []
        fastLapsPerClass = {}
        rawCarData = raw[0]

        for car in rawCarData.values():
            lastLap = parseTime(car["8"])
            carClass = self.staticData["tabEngages"][car["2"]]["categorie"]
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
            engage = self.staticData["tabEngages"][car["2"]]
            voiture = self.staticData["tabVehicules"][engage['voiture']]
            marque = self.staticData["tabMarques"][voiture['marque']]
            driver = self.staticData["tabPilotes"][car["5"]]
            team = self.staticData["tabTeams"][engage["team"]]
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

        state = {
            "flagState": FlagStatus.SC.name.lower() if course["9"] == 1 else mapFlagStates(course["6"]),
            "timeElapsed": parseSessionTime(course["4"]),
            "timeRemain": 0 if "7" not in course or course["7"][0] == "-" else parseSessionTime(course["7"])
        }

        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://live.fiawec.com/wpphpFichiers/1/live/FIAWEC/data.js?tx={}&t={}".format(
            "",
            int(time.time() / 15)
        )
        feed = urllib2.urlopen(feed_url)
        return simplejson.loads(feed.read())

    def createMessages(self, oldState, newState):
        messages = super(WEC, self).createMessages(oldState, newState)
        for newCar in newState["cars"]:
            oldCars = [c for c in oldState["cars"] if c[0] == newCar[0]]
            if oldCars:
                oldCar = oldCars[0]
                if newCar[1] != oldCar[1]:  # Change state
                    if newCar[1] == "PIT":
                        messages.append([int(time.time()), newCar[2], u"#{} ({}) has entered the pits".format(newCar[0], newCar[4]), "pit"])
                    elif newCar[1] == "OUT":
                        messages.append([int(time.time()), newCar[2], u"#{} ({}) has left the pits".format(newCar[0], newCar[4]), "out"])
                    elif newCar[1] == "RET":
                        messages.append([int(time.time()), newCar[2], u"#{} ({}) has retired".format(newCar[0], newCar[4]), ""])
        return messages


def main():
    Logger().info("Starting WEC timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(WEC)

if __name__ == '__main__':
    main()
