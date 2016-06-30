from livetiming.messages import CarPitMessage, DriverChangeMessage, FastLapMessage
from livetiming.service import JSONFetcher, Service as lt_service
from datetime import datetime
from twisted.logger import Logger
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


class Service(lt_service):
    log = Logger()

    def __init__(self, config):
        lt_service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        timingFetcher = JSONFetcher("http://multimedia.netstorage.imsa.com/scoring_data/RaceResults.json", self.parseTiming, 5)
        timingFetcher.start()
        sessionFetcher = JSONFetcher("http://multimedia.netstorage.imsa.com/scoring_data/SessionInfo.json", self.parseSession, 5)
        sessionFetcher.start()
        raceStateFetcher = JSONFetcher("http://multimedia.netstorage.imsa.com/scoring_data/RaceData.json", self.parseRaceState, 5)
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
        return {"cars": self.carsState, "session": self.sessionState}

    def parseTiming(self, raw):
        cars = []
        fastLapsPerClass = {}
        carList = [car for car in raw['B'] if car["C"] != ""]
        for car in carList:
            lastLap = parseTime(car["BL"])
            carClass = car["C"]
            if lastLap > 0 and (carClass not in fastLapsPerClass or fastLapsPerClass[carClass] > lastLap):
                fastLapsPerClass[carClass] = lastLap

        def getFlags(carClass, last, best):
            if carClass in fastLapsPerClass and last == fastLapsPerClass[carClass]:
                if last == best:
                    return "sb-new"
                return "sb"
            elif last == best and last > 0:
                return "pb"
            return ""

        for car in sorted(carList, key=lambda car: car["A"]):
            lastLap = parseTime(car["LL"])
            bestLap = parseTime(car["BL"])
            cars.append([
                car["N"],
                "PIT" if car["P"] == 1 else "RUN",
                car["C"],
                car["V"],
                car["F"],
                car["L"],
                car["D"],
                car["G"],
                [lastLap, getFlags(car["C"], lastLap, bestLap)],
                [bestLap, getFlags(car["C"], bestLap, -1)],
                car["PS"]
            ])

        self.carsState = cars

    def getMessageGenerators(self):
        return super(Service, self).getMessageGenerators() + [
            CarPitMessage(lambda c: c[1], lambda c: c[2], lambda c: c[4]),
            DriverChangeMessage(lambda c: c[2], lambda c: c[4]),
            FastLapMessage(lambda c: c[8], lambda c: c[2], lambda c: c[4])
        ]

    def parseSession(self, raw):
        self.sessionState["timeElapsed"] = parseSessionTime(raw["TT"])
        self.sessionState["timeRemain"] = parseSessionTime(raw["TR"])

    def parseRaceState(self, raw):
        self.sessionState["flagState"] = mapFlagStates(int(raw["C"]))
