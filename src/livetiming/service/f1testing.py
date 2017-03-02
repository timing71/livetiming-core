from livetiming.service import Service as lt_service, Fetcher
import simplejson
from livetiming.racing import Stat
from datetime import date


def find_todays_data(all_data):
    today = date.today().isoformat()
    for key, tests in all_data.iteritems():
        for day, test in tests.iteritems():
            if "date" in test and test["date"] == today:
                test["description"] = "{} - {}".format(key, day)
                return test
    return {}


class Service(lt_service):
    def __init__(self, config):
        super(Service, self).__init__(config)
        self.data = {}

        def setData(new_data):
            all_data = simplejson.loads(new_data[28:-2])
            old_description = self.data.get("description", None)
            self.data = find_todays_data(all_data)
            if self.data.get("description", None) != old_description:
                self.publishManifest()

        fetcher = Fetcher("http://www.softpauer.com/f1/2017/testsessions/TestResults.js", setData, 30)
        fetcher.start()

    def getName(self):
        return "F1 Testing"

    def getDefaultDescription(self):
        if "description" in self.data:
            return self.data["description"]
        return ""

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
        stats = self.data

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
                "flagState": "green" if stats["isSessionLive"] else "none",
                "timeElapsed": 0,
                "timeRemain": -1
            },
            "cars": cars
        }
