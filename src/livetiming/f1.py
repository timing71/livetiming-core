from livetiming.service import Service
from threading import Thread
from time import sleep
from twisted.logger import Logger
from os import environ
import simplejson
import random
import re
import urllib2
import xml.etree.ElementTree as ET
from autobahn.twisted.wamp import ApplicationRunner
from livetiming.messaging import Realm


class Fetcher(Thread):
    def __init__(self, url, callback, interval):
        Thread.__init__(self)
        self.url = url
        self.callback = callback
        self.interval = interval
        self.setDaemon(True)

    def run(self):
        while True:
            try:
                feed = urllib2.urlopen(self.url)
                self.callback(feed.readlines())
            except:
                pass  # Bad data feed :(
            sleep(self.interval)


def mapTimeFlag(color):
    timeMap = {
        "P": "sb",
        "G": "pb",
        "Y": "old"
    }
    if color in timeMap:
        return timeMap[color]
    return ""


def getServerConfig():
    serverListXML = urllib2.urlopen("http://www.formula1.com/sp/static/f1/2016/serverlist/svr/serverlist.xml")
    servers = ET.parse(serverListXML)
    race = "Catalunya"  # servers.getroot().attrib['race']
    session = "Practice3"  # servers.getroot().attrib['session']
    serverIP = random.choice(servers.findall('Server')).get('ip')
    return "http://{}/f1/2016/live/{}/{}/".format(serverIP, race, session)


class F1(Service):

    DATA_REGEX = re.compile(r"^(?:SP\._input_\(')([a-z]+)(?:',)(.*)\);$")

    def __init__(self, config):
        Service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        server_base_url = getServerConfig()
        self.dataMap = {}
        allURL = server_base_url + "all.js"
        allFetcher = Fetcher(allURL, self.processData, 60)
        allFetcher.start()
        curFetcher = Fetcher(server_base_url + "cur.js", self.processData, 1)
        curFetcher.start()
        self.processData(urllib2.urlopen(allURL).readlines())

    def processData(self, data):
        for dataline in data:
            matches = self.DATA_REGEX.match(dataline)
            if matches:
                self.dataMap[matches.group(1)] = simplejson.loads(matches.group(2))

    def getName(self):
        return "Formula 1"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("Driver", "text"),
            ("S1", "time"),
            ("BS1", "time"),
            ("S2", "time"),
            ("BS2", "time"),
            ("S3", "time"),
            ("BS3", "time"),
            ("Last", "time"),
            ("Gap", "time"),
            ("Int", "time"),
            ("Best", "time"),
        ]

    def getPollInterval(self):
        return 1

    def getRaceState(self):
        cars = []
        drivers = []
        bestTimes = []
        latestTimes = []
        for key, val in self.dataMap["init"].iteritems():
            if key != "T" and key != "TY":
                drivers = val["Drivers"]

        for key, val in self.dataMap["b"].iteritems():
            if key != "T" and key != "TY":
                bestTimes = val["DR"]

        for key, val in self.dataMap["o"].iteritems():
            if key != "T" and key != "TY":
                latestTimes = val["DR"]

        for idx, driver in enumerate(drivers):
            timeLine = bestTimes[idx]["B"].split(",")
            latestTimeLine = latestTimes[idx]["O"].split(",")
            colorFlags = latestTimeLine[2]

            cars.append([
                driver["Num"],
                driver["FullName"],
                [latestTimeLine[5], mapTimeFlag(colorFlags[1])],
                timeLine[4],
                [latestTimeLine[6], mapTimeFlag(colorFlags[2])],
                timeLine[7],
                [latestTimeLine[7], mapTimeFlag(colorFlags[3])],
                timeLine[10],
                [latestTimeLine[1], mapTimeFlag(colorFlags[0])],
                0,
                0,
                timeLine[1]
            ])

            cars.sort(key=lambda c: float(c[-1]) if c[-1] != "" else 9999)
            gap = 0
            for idx, car in enumerate(cars):
                if idx == 0:
                    car[9] = 0
                    car[10] = 0
                else:
                    prevCarTime = float(cars[idx - 1][-1])
                    interval = float(car[-1]) - prevCarTime
                    gap += interval
                    car[9] = gap
                    car[10] = interval

        return {"cars": cars, "session": {"flagState": "none", "timeElapsed": 0, "timeRemaining": 0}}


def main():
    Logger().info("Starting F1 timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(F1)

if __name__ == '__main__':
    main()