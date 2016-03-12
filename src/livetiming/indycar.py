from livetiming.service import Service
import urllib2
import simplejson
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


def parseTime(formattedTime):
    ttime = datetime.strptime(formattedTime, "%M:%S.%f")
    return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


class IndyCar(Service):
    log = Logger()

    def getName(self):
        return "IndyCar"

    def getDescription(self):
        return "IndyCar"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Driver", "text"),
            ("Laps", "numeric"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("Last", "time"),
            ("Last Spd", "numeric"),
            ("Best", "time"),
            ("Pits", "numeric")
        ]

    def getPollInterval(self):
        return 20

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []
        timingResults = raw['timing_results']
        for car in sorted(timingResults["Item"], key=lambda car: car["overallRank"]):
            cars.append([
                car["no"],
                "PIT" if car["status"] == "In Pit" else "OUT",
                "{0} {1}".format(car["firstName"], car["lastName"]),
                car["laps"],
                car["gap"],
                car["diff"],
                parseTime(car["lastLapTime"]),
                car["LastSpeed"],
                parseTime(car["bestLapTime"]),
                car["pitStops"]
            ])
        heartbeat = timingResults['heartbeat']
        state = {
            "flagState": mapFlagStates(heartbeat["currentFlag"]),
            "timeElapsed": heartbeat["elapsedTime"],
            "timeRemain": -1
        }
        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://racecontrol.indycar.com/xml/timingscoring.json"
        feed = urllib2.urlopen(feed_url)
        lines = feed.readlines()
        return simplejson.loads(lines[1])


def main():
    Logger().info("Starting IndyCar timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(IndyCar)

if __name__ == '__main__':
    main()
