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


def getServerConfig():
    serverListXML = urllib2.urlopen("http://www.formula1.com/sp/static/f1/2016/serverlist/svr/serverlist.xml")
    servers = ET.parse(serverListXML)
    race = "Catalunya"  # servers.getroot().attrib['race']
    session = "Practice2"  # servers.getroot().attrib['session']
    serverIP = random.choice(servers.findall('Server')).get('ip')
    return "http://{}/f1/2016/live/{}/{}/".format(serverIP, race, session)


class F1(Service):

    DATA_REGEX = re.compile(r"^(?:SP\._input_\(')([a-z]+)(?:',)(.*)\);$")

    def __init__(self, config):
        Service.__init__(self, config)
        self.carsState = []
        self.sessionState = {}
        server_base_url = getServerConfig()
        allURL = server_base_url + "all.js"
        allFetcher = Fetcher(allURL, self.processData, 60)
        allFetcher.start()
        self.processData(urllib2.urlopen(allURL).readlines())

    def processData(self, data):
        dataMap = {}
        for dataline in data:
            print ">>"
            matches = self.DATA_REGEX.match(dataline)
            if matches:
                dataMap[matches.group(1)] = simplejson.loads(matches.group(2))
        print dataMap


def main():
    Logger().info("Starting F1 timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(F1)

if __name__ == '__main__':
    main()