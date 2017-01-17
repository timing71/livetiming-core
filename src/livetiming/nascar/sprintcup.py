from livetiming.service import Service as lt_service
import urllib2
import simplejson
import random
from twisted.logger import Logger
from livetiming.racing import FlagStatus, Stat


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


class Service(lt_service):
    log = Logger()

    def getName(self):
        return "NASCAR Sprint Cup"

    def getDefaultDescription(self):
        return "NASCAR Sprint Cup"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.LAST_LAP,
            Stat.SPEED,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getPollInterval(self):
        return 20

    def getRaceState(self):
        raw = self.getRawFeedData()
        cars = []
        prevCar = None
        for car in sorted(raw["vehicles"], key=lambda car: car["running_position"]):
            cars.append([
                car["vehicle_number"],
                "RUN" if car["is_on_track"] else "PIT",
                car["driver"]["full_name"],
                car["laps_completed"],
                car["delta"],
                "-" if prevCar is None else car["delta"] - prevCar["delta"],
                car["last_lap_time"],
                car["last_lap_speed"],
                car["best_lap_time"],
                len(car["pit_stops"])
            ])
            prevCar = car
        state = {
            "flagState": mapFlagStates(raw["flag_state"]),
            "timeElapsed": raw["elapsed_time"],
            "timeRemain": -1
        }
        return {"cars": cars, "session": state}

    def getRawFeedData(self):
        feed_url = "http://www.nascar.com/live/feeds/series_1/4481/live_feed.json?random={}".format(random.randint(1, 1024))
        feed = urllib2.urlopen(feed_url)
        return simplejson.load(feed)
