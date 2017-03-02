from livetiming.service import Service as lt_service, Fetcher
import simplejson
from livetiming.racing import Stat


class Service(lt_service):
    def __init__(self, config):
        super(Service, self).__init__(config)
        self.data = None

        def setData(new_data):
            self.data = simplejson.loads(new_data[28:-2])

        fetcher = Fetcher("http://www.softpauer.com/f1/2017/testsessions/TestResults.js", setData, 30)
        fetcher.start()

    def getName(self):
        return "F1 Testing"

    def getDefaultDescription(self):
        return "Barcelona day 4"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.LAPS,
            Stat.BEST_LAP,
            Stat.GAP,
            Stat.INT,
            Stat.PITS
        ]

    def getRaceState(self):
        cars = []

        if "F1 Team Testing - T01 - Barcelona" in self.data:
            barca = self.data["F1 Team Testing - T01 - Barcelona"]
            if "Thursday" in barca:
                stats = barca["Thursday"]

                drivers = {}
                for driver in stats["testEntry"]:
                    drivers[driver["racingNumber"]] = driver

                for car in stats["testClassification"]:
                    driver = drivers[car["racingNumber"]]

                    cars.append([
                        car["racingNumber"],
                        "PIT" if car["inPits"] else "RUN",
                        driver["driverFullName"],
                        driver["teamName"],
                        car["lapNumber"],
                        car["lapTimeL"] / 1000.0,
                        car["gap"],
                        car["difference"],
                        car["pitStops"]
                    ])
        return {
            "session": {
                "flagState": "green" if stats["isSessionLive"] else "red",
                "timeElapsed": 0,
                "timeRemain": -1
            },
            "cars": cars
        }
