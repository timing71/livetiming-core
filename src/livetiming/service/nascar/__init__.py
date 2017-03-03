from livetiming.service import Service as lt_service
import urllib2
import simplejson
import random
from twisted.logger import Logger
from livetiming.racing import FlagStatus, Stat
import re
import logging


def mapFlagStates(rawState):
    flagMap = {
        1: FlagStatus.GREEN,
        2: FlagStatus.FCY,
        3: FlagStatus.RED,
        4: FlagStatus.CHEQUERED,
        5: FlagStatus.WHITE,
        8: FlagStatus.YELLOW,  # "warm" whatever that means
        10: FlagStatus.WHITE
    }
    if rawState in flagMap:
        return flagMap[rawState].name.lower()
    return "none"


class Service(lt_service):
    log = Logger()

    def __init__(self, config):
        super(Service, self).__init__(config)
        self.description = ""
        self.feedURL = None

    def getName(self):
        return "NASCAR"

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.LAST_LAP,
            Stat.SPEED,
            Stat.BEST_LAP,
            Stat.BEST_SPEED,
            Stat.PITS
        ]

    def getPollInterval(self):
        return 5

    def getRaceState(self):
        raw = self.getRawFeedData()

        if "run_name" in raw and raw["run_name"] != self.description:
            self.description = raw["run_name"]
            self.publishManifest()

        cars = []

        bestLapCar = None
        bestLapTime = None

        for car in sorted(raw["vehicles"], key=lambda car: car["running_position"]):

            if car["best_lap_time"] > 0 and (bestLapCar is None or bestLapTime > car["best_lap_time"]):
                bestLapCar = len(cars)
                bestLapTime = car["best_lap_time"]

            last_lap_flag = "pb" if car["best_lap_time"] == car["last_lap_time"] else ""
            cars.append([
                car["vehicle_number"],
                "RUN" if car["is_on_track"] else "PIT",
                car["driver"]["full_name"].replace("#", "").replace("*", "").replace("(i)", "").strip(),
                car["vehicle_manufacturer"],
                car["laps_completed"],
                car["delta"],
                "" if len(cars) == 0 or car["best_lap_time"] == 0 else car["delta"] if len(cars) == 1 else car["delta"] - cars[-1][5],
                (car["last_lap_time"], last_lap_flag),
                car["last_lap_speed"],
                (car["best_lap_time"], ""),
                car["best_lap_speed"],
                len(car["pit_stops"])
            ])

        if bestLapCar:
            bestCar = cars[bestLapCar]
            if bestCar[7][0] == bestCar[9][0]:
                bestCar[7] = (bestCar[7][0], "sb-new")
            bestCar[9] = (bestCar[9][0], "sb")

        state = {
            "flagState": mapFlagStates(raw["flag_state"]),
            "timeElapsed": raw["elapsed_time"],
            "timeRemain": -1
        }

        if raw["run_type"] == 3:  # race (1 = practice, 2 = quali
            state["lapsRemain"] = raw["laps_to_go"]

        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        url = "{}".format(self._getFeedURL())
        self.log.debug("Using url {}".format(url))
        try:
            request = urllib2.Request(url)
            request.add_header("User-Agent", "livetiming")
            feed = urllib2.urlopen(request)
            return simplejson.load(feed)
        except Exception as e:
            print e

    def getSeriesTag(self):
        return ""

    def _getFeedURL(self):
        if not self.feedURL:
            series = self.getSeriesTag()
            self.log.info("Retrieving feed URL from http://www.nascar.com/{}racecenter".format(series))
            raw = None
            while raw is None or raw.getcode() != 200:
                rq = urllib2.Request("http://www.nascar.com/{}racecenter".format(series))
                rq.add_header("User-Agent", "livetiming")
                raw = urllib2.urlopen(rq)
            m = re.search("http://www.nascar.com/live/feeds/series.*\.json", raw.read())
            self.feedURL = m.group(0)
            self.log.info("Using feed URL {}".format(self.feedURL))
        return self.feedURL
