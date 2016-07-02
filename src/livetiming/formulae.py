# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import FastLapMessage, TimingMessage
from livetiming.racing import FlagStatus
from livetiming.service import JSONFetcher, Service as lt_service
import urllib2
import simplejson


def parseTime(rawTime):
    try:
        parsedValue = int(rawTime)
        if parsedValue > 3599990:
            return ""
        return parsedValue / 1000.0
    except:
        return rawTime


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


def mapFlagStates(rawState):
    flagMap = {
        "Finish": FlagStatus.CHEQUERED,
        "Green": FlagStatus.GREEN,
        "Yellow": FlagStatus.YELLOW,
        # What else goes here?
    }
    if rawState in flagMap:
        return flagMap[rawState].name.lower()
    return "none"


class RaceControlMessage(TimingMessage):
    def _consider(self, oldState, newState):
        if newState["raceControlMessage"] is not None:
            msg = newState["raceControlMessage"]
            return ["Race Control", msg, "raceControl"]


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        self.sessionID = self._getSessionID()

        self.carState = []
        self.carFetcher = JSONFetcher(
            "http://telemetry.dc-formulae.com/api/timing/all?sessionid={}".format(self.sessionID),
            self.processCarData,
            1
        )
        self.carFetcher.start()

        self.sessionState = {"flagState": 'none'}
        self.trackFetcher = JSONFetcher(
            "http://telemetry.dc-formulae.com/api/track?sessionid={}".format(self.sessionID),
            self.processTrackData,
            1
        )
        self.trackFetcher.start()

        self.currentMessage = None
        self.lastMessage = None

    def getName(self):
        return "FIA Formula E"

    def getDescription(self):
        return "FIA Formula E"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("Driver", "text"),
            ("Team", "text"),
            ("Laps", "numeric"),
            ("Gap", "delta"),
            ("Int", "delta"),
            ("Last", "time"),
            ("S1", "time"),
            ("S2", "time"),
            ("S3", "time"),
            ("Best", "time")
        ]

    def getTrackDataSpec(self):
        return [
            "Temp",
            "Humidity",
            "Wind Speed",
            "Direction",
            "Pressure",
            "Rain"
        ]

    def getPollInterval(self):
        return 1

    def getRaceState(self):
        state = {
            "cars": self.carState,
            "session": self.sessionState,
            "raceControlMessage": self.currentMessage if self.currentMessage != self.lastMessage else None
        }
        self.lastMessage = self.currentMessage
        return state

    def processCarData(self, data):
        cars = []
        overallBests = [99999, 99999, 99999, 99999]
        if "data" in data:
            for car in sorted([car for car in data["data"].itervalues() if "id" in car], key=lambda car: int(car["pos"]) if car["pos"] != "" else 0):
                gap = parseTime(car["gap"])

                bests = [
                    parseTime(car["best_sector_1"]),
                    parseTime(car["best_sector_2"]),
                    parseTime(car["best_sector_3"]),
                ]

                lastLap = parseTime(car["lap_time"])
                lastS1 = parseTime(car["sector_1"])
                lastS2 = parseTime(car["sector_2"])
                lastS3 = parseTime(car["sector_3"])
                bestLap = parseTime(car["best_lap"])

                overallBests = [
                    min(bestLap, overallBests[0]),
                    min(bests[0], overallBests[1]),
                    min(bests[1], overallBests[2]),
                    min(bests[2], overallBests[3])
                ]
                
                cars.append([
                    car["id"],
                    car["name"],
                    car["team"],
                    car["laps"],
                    gap,
                    gap - cars[-1][4] if cars and isinstance(cars[-1][4], float) and isinstance(gap, float) else "",
                    [lastLap, "pb" if lastLap == bestLap else ""],
                    [lastS1, "pb" if lastS1 == bests[0] else ""],
                    [lastS2, "pb" if lastS2 == bests[1] else ""],
                    [lastS3, "pb" if lastS3 == bests[2] else ""],
                    [parseTime(car["best_lap"]), ""]
                ])

            # Annotate overall best times
            for car in cars:
                if car[6][0] == overallBests[0]:
                    car[6][1] = "sb-new"
                if car[7][0] == overallBests[1]:
                    car[7][1] = "sb"
                if car[8][0] == overallBests[2]:
                    car[8][1] = "sb"
                if car[9][0] == overallBests[3]:
                    car[9][1] = "sb"
                if car[10][0] == overallBests[0]:
                    car[10][1] = "sb"

        self.carState = cars

    def processTrackData(self, data):
        if "data" in data:
            trackData = data["data"]["track"]
            self.sessionState = {
                "flagState": mapFlagStates(trackData["flag"]),
                "timeElapsed": parseSessionTime(trackData["racetime"]),
                "timeRemain": parseSessionTime(trackData["time_to_go"]),
                "trackData": [
                    u"{:.3g}°C".format(float(trackData["temperature"])),
                    "{}%".format(trackData["humidity"]),
                    "{:.2g}kph".format(float(trackData["wind_speed"])),
                    u"{}°".format(trackData["wind_direction"]),
                    "{}mbar".format(trackData["pressure"]),
                    "{}%".format(trackData["rain"])
                ]
            }
            self.currentMessage = trackData["message"]

    def getMessageGenerators(self):
        return super(Service, self).getMessageGenerators() + [
            FastLapMessage(lambda c: c[6], lambda c: "Timing", lambda c: c[1]),
            RaceControlMessage()
        ]

    def _getSessionID(self):
        sessionURL = "http://telemetry.dc-formulae.com/api/timing/sessionid?sessionid=911cfcbe-1973-4c9c-b6f3-19cbfadeb00f"
        sessionFeed = urllib2.urlopen(sessionURL)
        session = simplejson.loads(sessionFeed.read())
        return session["sessionid"]
