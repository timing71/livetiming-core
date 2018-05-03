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


def parseSpeed(formatted):
    if formatted == '':
        return 0
    try:
        return float(formatted)
    except ValueError:
        return 0


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


def map_tyre(raw_tyre):
    mapp = {
        'P': ["P", "tyre-medium"],
        'A': ["O", "tyre-ssoft"],
        'W': ["W", "tyre-wet"],
        'WX': ["W", "tyre-wet"]
    }
    if raw_tyre in mapp:
        return mapp[raw_tyre]
    return raw_tyre


class Service(lt_service):
    attribution = ['IndyCar', 'http://racecontrol.indycar.com/']
    log = Logger()

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.name = "IndyCar"
        self.description = "IndyCar"
        self._oval_mode = False

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
            Stat.INT
        ] + self._get_sector_colspec() + [
            Stat.LAST_LAP,
            Stat.SPEED,
            Stat.BEST_LAP,
            Stat.BEST_SPEED,
            Stat.PITS
        ]

    def _get_sector_colspec(self):
        if self._oval_mode:
            return [
                Stat.T1_SPEED,
                Stat.BEST_T1_SPEED,
                Stat.T3_SPEED,
                Stat.BEST_T3_SPEED
            ]
        else:
            return [
                Stat.S1,
                Stat.BS1,
                Stat.S2,
                Stat.BS2,
                Stat.S3,
                Stat.BS3
            ]

    def getPollInterval(self):
        return 5

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []

        timingResults = raw['timing_results']

        heartbeat = timingResults['heartbeat']

        shouldRepublish = False
        trackType = heartbeat.get('trackType', None)
        if trackType == "I" or trackType == "O":
            shouldRepublish = not self._oval_mode
            self._oval_mode = True
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

        seen = set()
        filtered = [seen.add(car["no"]) or car for car in timingResults["Item"] if car["no"] not in seen]

        fastSectors = [[0, None], [0, None]] if self._oval_mode else [[9999, None], [9999, None], [9999, None]]
        fastLap = [9999, None]

        for car in sorted(filtered, key=lambda car: int(car["rank"])):
            lastLapTime = parseTime(car["lastLapTime"])
            bestLapTime = parseTime(car["bestLapTime"])

            if bestLapTime > 0 and bestLapTime < fastLap[0]:
                fastLap = [bestLapTime, car['no']]

            if self._oval_mode:
                t1 = parseSpeed(car.get('T1_SPD', 0))
                bt1 = parseSpeed(car.get('Best_T1_SPD', 0))

                t3 = parseSpeed(car.get('T3_SPD', ''))
                bt3 = parseSpeed(car.get('Best_T3_SPD', ''))

                if bt1 > 0 and bt1 > fastSectors[0][0]:
                    fastSectors[0] = (bt1, car['no'])
                if bt3 > 0 and bt3 > fastSectors[1][0]:
                    fastSectors[1] = (bt3, car['no'])

                sector_cols = [
                    (t1 if t1 > 0 else '', 'pb' if t1 == bt1 else ''),
                    (bt1 if bt1 > 0 else '', 'old'),
                    (t3 if t3 > 0 else '', 'pb' if t3 == bt3 else ''),
                    (bt3 if bt3 > 0 else '', 'old')
                ]
            else:

                bs1 = parseTime(car.get('Best_I1', 0))
                if bs1 > 0 and bs1 < fastSectors[0][0]:
                    fastSectors[0] = [bs1, car['no']]
                bs2 = parseTime(car.get('Best_I2', 0))
                if bs2 > 0 and bs2 < fastSectors[1][0]:
                    fastSectors[1] = [bs2, car['no']]
                bs3 = parseTime(car.get('Best_I3', 0))
                if bs3 > 0 and bs3 < fastSectors[2][0]:
                    fastSectors[2] = [bs3, car['no']]

                s1 = car.get('I1', '')
                s2 = car.get('I2', '')
                s3 = car.get('I3', '')

                sector_cols = [
                    [s1, 'pb' if s1 == car.get('Best_I1', None) else ''],
                    [car.get('Best_I1', ''), 'old'],
                    [s2, 'pb' if s2 == car.get('Best_I2', None) else ''],
                    [car.get('Best_I2', ''), 'old'],
                    [s3, 'pb' if s3 == car.get('Best_I3', None) else ''],
                    [car.get('Best_I3', ''), 'old']
                ]

            diff = car.get('diff', '-')
            gap = car.get('gap', 0)

            cars.append([
                car["no"],
                "PIT" if (car["status"] == "In Pit" or car["onTrack"] == "False") else "RUN",
                "{0} {1}".format(car.get("firstName", ""), car.get("lastName", "")),
                car["laps"],
                map_tyre(car.get('Tire', '')),
                [car["OverTake_Remain"], "ptp-active" if car["OverTake_Active"] == 1 else ""],
                diff if diff[0] != '-' and diff != '0.0000' else '',
                gap if gap > 0 and gap != '0.0000' else '',
            ] + sector_cols + [
                [lastLapTime if lastLapTime > 0 else '', "pb" if lastLapTime == bestLapTime and bestLapTime > 0 else ""],
                car["LastSpeed"] if "LastSpeed" in car else "",
                [bestLapTime if bestLapTime > 0 else '', ""],
                car.get('BestSpeed', ''),
                car["pitStops"]
            ])

        bestLapIdx = 14 if self._oval_mode else 16
        lastLapIdx = 12 if self._oval_mode else 14
        lastSectorIdx = 10 if self._oval_mode else 12

        for car in cars:
            num = car[0]
            if num == fastLap[1]:
                car[bestLapIdx] = [car[bestLapIdx][0], 'sb']
                if car[bestLapIdx][0] == car[lastLapIdx][0]:
                    car[lastLapIdx] = [car[lastLapIdx][0], 'sb-new' if car[lastSectorIdx][0] != '' else 'sb']
            if num == fastSectors[0][1]:
                car[9] = [car[9][0], 'sb']
                if car[8][0] == car[9][0]:
                    car[8] = [car[8][0], 'sb']
            if num == fastSectors[1][1]:
                car[11] = [car[11][0], 'sb']
                if car[10][0] == car[11][0]:
                    car[10] = [car[10][0], 'sb']
            if not self._oval_mode and num == fastSectors[1][1]:
                car[13] = [car[13][0], 'sb']
                if car[12][0] == car[13][0]:
                    car[12] = [car[12][0], 'sb']

        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://racecontrol.indycar.com/xml/timingscoring.json"
        feed = urllib2.urlopen(feed_url)
        lines = feed.readlines()
        return simplejson.loads(lines[1])
