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
        1: FlagStatus.GREEN,
        2: FlagStatus.YELLOW,
        3: FlagStatus.RED,
        4: FlagStatus.CHEQUERED,
        5: FlagStatus.WHITE,
        10: FlagStatus.WHITE
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
        "1": "lmp1",
        "2": "gtpro",
        "3": "lmp2",
        "4": "gtam"
    }
    return classMap[rawClass]


def parseTime(formattedTime):
    ttime = datetime.strptime(formattedTime, "%M:%S.%f")
    return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def hackDataFromJSONP(data, var):
    return simplejson.loads(re.search(r'(?:%s = jQuery\.parseJSON\(\')([^\;]+)(?:\'\)\;)' % var, data).group(1))


def getStaticData():
    Logger().info("Retrieving WEC static data...")
    static_data_url = "http://live.fiawec.com/wpphpFichiers/1/live/referentiel_470.js"
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
            ("Cat", "text"),
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

        rawCarData = raw[0]
        for pos in sorted(rawCarData.iterkeys(), key=lambda i: int(i)):
            car = rawCarData[pos]
            engage = self.staticData["tabEngages"][car["2"]]
            voiture = self.staticData["tabVehicules"][engage['voiture']]
            marque = self.staticData["tabMarques"][voiture['marque']]
            driver = self.staticData["tabPilotes"][car["5"]]
            team = self.staticData["tabTeams"][engage["team"]]
            classe = engage["categorie"]

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
                parseTime(car["12"]),  # last lap
                parseTime(car["8"]),  # best lap
                car["1"],  # ave speed
                car["20"]  # pits
            ])

        state = {}

        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://live.fiawec.com/wpphpFichiers/1/live/FIAWEC/data.js?tx={}&t={}".format(
            "",
            int(time.time() / 15)
        )
        feed = urllib2.urlopen(feed_url)
        return simplejson.loads(feed.read())


def main():
    Logger().info("Starting WEC timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(WEC)

if __name__ == '__main__':
    main()
