from livetiming.service import Service
import urllib2
import simplejson
from datetime import datetime
from twisted.logger import Logger
from os import environ
from autobahn.twisted.wamp import ApplicationRunner
from livetiming.messaging import Realm
from livetiming.racing import FlagStatus
from time import sleep
from threading import Thread


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


def parseTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        return 0


def parseSessionTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S")
        return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        return 0


class IMSAFetcher(Thread):
    def __init__(self, url, callback, interval):
        Thread.__init__(self)
        self.url = url
        self.callback = callback
        self.interval = interval
        self.setDaemon(True)

    def run(self):
        while True:
            feed = urllib2.urlopen(self.url)
            self.callback(simplejson.load(feed))
            sleep(self.interval)


class IMSA(Service):
    log = Logger()

    def __init__(self, config):
        Service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        timingFetcher = IMSAFetcher("http://multimedia.netstorage.imsa.com/scoring_data/RaceResults.json", self.parseTiming, 5)
        timingFetcher.start()
        sessionFetcher = IMSAFetcher("http://multimedia.netstorage.imsa.com/scoring_data/SessionInfo.json", self.parseSession, 5)
        sessionFetcher.start()
        raceStateFetcher = IMSAFetcher("http://multimedia.netstorage.imsa.com/scoring_data/RaceData.json", self.parseRaceState, 5)
        raceStateFetcher.start()

    def getName(self):
        return "IMSA"

    def getDescription(self):
        return "IMSA WeatherTech and support championships"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Class", "text"),
            ("Car", "text"),
            ("Driver", "text"),
            ("Laps", "numeric"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "numeric")
        ]

    def getPollInterval(self):
        return 5

    def getRaceState(self):
        result = {"cars": self.carsState, "session": self.sessionState}
        print result
        return result

    def parseTiming(self, raw):
        cars = []
        carList = [car for car in raw['B'] if car["C"] != ""]
        for car in sorted(carList, key=lambda car: car["A"]):
            cars.append([
                car["N"],
                "PIT" if car["P"] == 1 else "RUN",
                car["C"],
                car["V"],
                car["F"],
                car["L"],
                car["D"],
                car["G"],
                parseTime(car["LL"]),
                parseTime(car["BL"]),
                car["PS"]
            ])

        self.carsState = cars

    def parseSession(self, raw):
        self.sessionState["timeElapsed"] = parseSessionTime(raw["TT"])
        self.sessionState["timeRemain"] = parseSessionTime(raw["TR"])

    def parseRaceState(self, raw):
        self.sessionState["flagState"] = mapFlagStates(int(raw["C"]))


def main():
    Logger().info("Starting IMSA timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(IMSA)

if __name__ == '__main__':
    main()
