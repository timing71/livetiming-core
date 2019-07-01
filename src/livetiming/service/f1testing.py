from datetime import date
from livetiming.racing import Stat
from livetiming.service import Service as lt_service, Fetcher

import sentry_sdk
import simplejson
from simplejson.scanner import JSONDecodeError


def find_todays_data(all_data):
    today = date.today().isoformat()
    for key, tests in all_data.items():
        for day, test in tests.items():
            if "date" in test and test["date"] == today:
                test["description"] = "{} - {}".format(key, day)
                return test
    return {}


class Service(lt_service):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.data = {}

        def setData(new_data):
            try:
                all_data = simplejson.loads(new_data[28:-2])
                old_description = self.data.get("description", None)
                self.data = find_todays_data(all_data)
                if self.data.get("description", None) != old_description:
                    self.publishManifest()
            except JSONDecodeError as e:
                self.log.failure("Failed parsing JSON. Exception was {log_failure}. Data was {data}.", data=e.doc)
                sentry_sdk.capture_exception(e)

        fetcher = Fetcher("http://www.softpauer.com/f1/2018/testsessions/TestResults.js", setData, 30)
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
        if "testEntry" in stats and "testClassification" in stats:
            for driver in stats["testEntry"]:
                drivers[driver["racingNumber"]] = driver

            for car in stats["testClassification"]:
                if car["racingNumber"] in drivers:
                    driver = drivers[car["racingNumber"]]
                else:
                    driver = {"driverFullName": car["driverLastName"], "teamName": "?"}

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
                "flagState": "none",
                "timeElapsed": 0
            },
            "cars": cars
        }
