from livetiming.messages import CarPitMessage, FastLapMessage
from livetiming.service import Service
import urllib2
import simplejson
from datetime import datetime
from twisted.logger import Logger
from os import environ
from autobahn.twisted.wamp import ApplicationRunner
from livetiming.network import Realm
from livetiming.racing import FlagStatus


def mapFlagStates(rawState):
    flagMap = {
        "GREEN": FlagStatus.GREEN,
        "YELLOW": FlagStatus.YELLOW,
        "RED": FlagStatus.RED,
        "CHECKERED": FlagStatus.CHEQUERED,
        "WHITE": FlagStatus.WHITE,
        "COLD": FlagStatus.NONE
    }
    if rawState in flagMap:
        return flagMap[rawState].name.lower()
    return "none"


def parseTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        ttime = datetime.strptime(formattedTime, "%S.%f")
        return ttime.second + (ttime.microsecond / 1000000.0)


def parseSessionTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S")
            return (60 * ttime.minute) + ttime.second
        except ValueError:
            return formattedTime


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
            ("T", "text"),
            ("PTP", "numeric"),
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
        seen = set()
        filtered = [seen.add(car["no"]) or car for car in timingResults["Item"] if car["no"] not in seen]
        for car in sorted(filtered, key=lambda car: int(car["overallRank"])):
            lastLapTime = parseTime(car["lastLapTime"])
            bestLapTime = parseTime(car["bestLapTime"])
            cars.append([
                car["no"],
                "PIT" if (car["status"] == "In Pit" or car["onTrack"] == "False") else "RUN",
                "{0} {1}".format(car["firstName"], car["lastName"]),
                car["laps"],
                (["P", "tyre-medium"] if car["Tire"] == "P" else ["O", "tyre-ssoft"]) if "Tire" in car else "",
                [car["OverTake_Remain"], "ptp-active" if car["OverTake_Active"] == 1 else ""],
                car["diff"],
                car["gap"],
                [lastLapTime, "pb" if lastLapTime == bestLapTime and bestLapTime > 0 else ""],
                car["LastSpeed"] if "LastSpeed" in car else "",
                [bestLapTime, ""],
                car["pitStops"]
            ])

        byFastestLap = sorted(cars, key=lambda c: float(c[10][0]) if c[10][0] != 0 else 9999)
        purpleCar = byFastestLap[0]
        purpleCar[10][1] = "sb"
        purpleCar[8][1] = "sb-new" if purpleCar[8][0] == purpleCar[10][0] and purpleCar[1] != "PIT" else ""

        heartbeat = timingResults['heartbeat']
        state = {
            "flagState": mapFlagStates(heartbeat["currentFlag"]),
            "timeElapsed": parseSessionTime(heartbeat["elapsedTime"]),
            "timeRemain": parseSessionTime(heartbeat["overallTimeToGo"]) if "overallTimeToGo" in heartbeat else 0,
        }
        if "totalLaps" in heartbeat:
            state["lapsRemain"] = int(heartbeat["totalLaps"]) - int(heartbeat["lapNumber"])
        return {"cars": cars, "session": state}

    def getMessageGenerators(self):
        return super(IndyCar, self).getMessageGenerators() + [
            CarPitMessage(lambda c: c[1], lambda c: "Pits", lambda c: c[2]),
            FastLapMessage(lambda c: c[7], lambda c: "Timing", lambda c: c[2])
        ]

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
