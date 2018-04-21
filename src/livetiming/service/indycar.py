from datetime import datetime
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from twisted.logger import Logger

import urllib2
import simplejson


def mapFlagStates(rawState):
    flagMap = {
        "GREEN": FlagStatus.GREEN,
        "YELLOW": FlagStatus.CAUTION,
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
        try:
            ttime = datetime.strptime(formattedTime, "%S.%f")
            return ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            try:
                ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
                return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
            except ValueError:
                return formattedTime
    except TypeError:
        return formattedTime  # which might actually be a number


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


def parseEventName(heartbeat):
    if "eventName" in heartbeat:
        event = "{} - ".format(heartbeat["eventName"])
    else:
        event = ""

    if "preamble" in heartbeat:
        session = heartbeat["preamble"]
        if session[0] == "R":
            return "{}Race".format(event)
        elif session[0] == "P":  # Practice
            if session[1].upper() == "F":
                return "{}Final Practice".format(event)
            return "{}Practice {}".format(event, session[1])
        elif session[0] == "Q":  # Qualifying
            track_type = heartbeat["trackType"] if "trackType" in heartbeat else None
            if track_type == "I" or track_type == "O":  # Indy 500 or other oval
                return "{}Qualifying".format(event)
            elif session[1] == "3":
                return "{}Qualifying - Round 2".format(event)
            elif session[1] == "4":
                return "{}Qualifying - Firestone Fast Six".format(event)
            else:
                return "{}Qualifying - Group {}".format(event, session[1])
        elif session[0] == "I":  # Indy 500 qualifying
            if session[1] == "4":
                return "{}Qualifying - Fast 9".format(event)
            return "{}Qualifying".format(event)
    return event


class Service(lt_service):
    attribution = ['IndyCar', 'http://racecontrol.indycar.com/']
    log = Logger()

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.name = "IndyCar"
        self.description = "IndyCar"

    def getName(self):
        return self.name

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.TYRE,
            Stat.PUSH_TO_PASS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.BS1,
            Stat.S2,
            Stat.BS2,
            Stat.S3,
            Stat.BS3,
            Stat.LAST_LAP,
            Stat.SPEED,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getPollInterval(self):
        return 5

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []
        timingResults = raw['timing_results']
        seen = set()
        filtered = [seen.add(car["no"]) or car for car in timingResults["Item"] if car["no"] not in seen]

        fastSectors = [[9999, None], [9999, None], [9999, None]]
        fastLap = [9999, None]

        for car in sorted(filtered, key=lambda car: int(car["rank"])):
            lastLapTime = parseTime(car["lastLapTime"])
            bestLapTime = parseTime(car["bestLapTime"])

            bs1 = parseTime(car.get('Best_I1', 0))
            if bs1 > 0 and bs1 < fastSectors[0][0]:
                fastSectors[0] = [bs1, car['no']]
            bs2 = parseTime(car.get('Best_I2', 0))
            if bs2 > 0 and bs2 < fastSectors[1][0]:
                fastSectors[1] = [bs2, car['no']]
            bs3 = parseTime(car.get('Best_I3', 0))
            if bs3 > 0 and bs3 < fastSectors[2][0]:
                fastSectors[2] = [bs3, car['no']]
            if bestLapTime > 0 and bestLapTime < fastLap[0]:
                fastLap = [bestLapTime, car['no']]

            s1 = car.get('I1', '')
            s2 = car.get('I2', '')
            s3 = car.get('I3', '')

            cars.append([
                car["no"],
                "PIT" if (car["status"] == "In Pit" or car["onTrack"] == "False") else "RUN",
                "{0} {1}".format(car.get("firstName", ""), car.get("lastName", "")),
                car["laps"],
                (["P", "tyre-medium"] if car["Tire"] == "P" else ["O", "tyre-ssoft"]) if "Tire" in car else "",
                [car["OverTake_Remain"], "ptp-active" if car["OverTake_Active"] == 1 else ""],
                car["diff"] if "diff" in car else "",
                car["gap"] if "gap" in car else "",
                [s1, 'pb' if s1 == car.get('Best_I1', None) else ''],
                [car['Best_I1'], 'old'],
                [s2, 'pb' if s2 == car.get('Best_I2', None) else ''],
                [car.get('Best_I2', ''), 'old'],
                [s3, 'pb' if s3 == car('Best_I3', None) else ''],
                [car['Best_I3'], 'old'],
                [lastLapTime, "pb" if lastLapTime == bestLapTime and bestLapTime > 0 else ""],
                car["LastSpeed"] if "LastSpeed" in car else "",
                [bestLapTime, ""],
                car["pitStops"]
            ])

        for car in cars:
            num = car[0]
            if num == fastLap[1]:
                car[16] = [car[16][0], 'sb']
                if car[16][0] == car[14][0]:
                    car[14] = [car[14][0], 'sb-new' if car[12][0] != '' else 'sb']
            if num == fastSectors[0][1]:
                car[9] = [car[9][0], 'sb']
                if car[8][0] == car[9][0]:
                    car[8] = [car[8][0], 'sb']
            if num == fastSectors[1][1]:
                car[11] = [car[11][0], 'sb']
                if car[10][0] == car[11][0]:
                    car[10] = [car[10][0], 'sb']
            if num == fastSectors[1][1]:
                car[13] = [car[13][0], 'sb']
                if car[12][0] == car[13][0]:
                    car[12] = [car[12][0], 'sb']

        heartbeat = timingResults['heartbeat']

        shouldRepublish = False
        if "Series" in heartbeat and heartbeat["Series"] != self.name:
            self.name = heartbeat["Series"]
            shouldRepublish = True
        eventName = parseEventName(heartbeat)
        if eventName != self.description:
            self.description = eventName
            shouldRepublish = True
        if shouldRepublish:
            self.analyser.reset()
            self.publishManifest()

        state = {
            "flagState": mapFlagStates(heartbeat["currentFlag"]),
            "timeElapsed": parseSessionTime(heartbeat["elapsedTime"]),
            "timeRemain": parseSessionTime(heartbeat["overallTimeToGo"]) if "overallTimeToGo" in heartbeat else 0,
        }
        if "totalLaps" in heartbeat:
            state["lapsRemain"] = int(heartbeat["totalLaps"]) - int(heartbeat["lapNumber"])
        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://racecontrol.indycar.com/xml/timingscoring.json"
        feed = urllib2.urlopen(feed_url)
        lines = feed.readlines()
        return simplejson.loads(lines[1])
