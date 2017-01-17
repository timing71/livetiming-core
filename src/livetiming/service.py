from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.twisted.util import sleep
from livetiming.messages import FlagChangeMessage, CarPitMessage,\
    DriverChangeMessage, FastLapMessage
from livetiming.network import Channel, Message, MessageClass, Realm, RPC
from livetiming.racing import FlagStatus, Stat
from livetiming.recording import TimingRecorder
from os import environ, path
from random import randint
from threading import Thread
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from uuid import uuid4
import argparse
import copy
import simplejson
import txaio
import time
import urllib2


class Service(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.args = config.extra
        self.uuid = path.splitext(self.args["initial_state"])[0] if self.args["initial_state"] is not None else uuid4().hex
        self.state = self.getInitialState()
        if self.args["recording_file"] is not None:
            self.recorder = TimingRecorder(self.args["recording_file"])
            self.recorder.writeManifest(self.createServiceRegistration())
        else:
            self.recorder = None

    def getInitialState(self):
        if self.args["initial_state"] is not None:
            try:
                stateFile = open(self.args["initial_state"], 'r')
                return simplejson.load(stateFile)
            except Exception as e:
                self.log.error("Exception trying to load saved state: {}".format(e))
            finally:
                stateFile.close()
        return {
            "messages": [],
            "session": {
                "flagState": "green",
                "timeElapsed": 0,
                "timeRemain": 0},
            "cars": []
        }

    def saveState(self):
        self.log.debug("Saving state of {}".format(self.uuid))
        try:
            stateFile = open("{}.json".format(self.uuid), 'w')
            simplejson.dump(self.state, stateFile)
        except Exception as e:
            self.log.error(e)
        finally:
            stateFile.close()
        if self.recorder:
            self.recorder.writeState(self.state)

    def createServiceRegistration(self):
        colspec = map(lambda s: s.value if isinstance(s, Stat) else s, self.getColumnSpec())
        return {
            "uuid": self.uuid,
            "name": self.getName(),
            "description": self.getDescription(),
            "colSpec": colspec,
            "trackDataSpec": self.getTrackDataSpec(),
            "pollInterval": self.getPollInterval()
        }

    def getName(self):
        return "Generic Service"

    def getDescription(self):
        if self.args['description'] is not None:
            return self.args['description']
        return self.getDefaultDescription()

    def getDefaultDescription(self):
        return "A generic service that has no purpose other than as a base class"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.LAST_LAP,
            Stat.PITS
        ]

    def getTrackDataSpec(self):
        return []

    def getPollInterval(self):
        return 10

    def isAlive(self):
        return True

    def _updateRaceState(self):
        try:
            newState = self.getRaceState()
            self.state["messages"] = (self.createMessages(self.state, newState) + self.state["messages"])[0:100]
            self.state["cars"] = copy.deepcopy(newState["cars"])
            self.state["session"] = copy.deepcopy(newState["session"])
            self.saveState()
        except Exception as e:
            self.log.error(e)

    def getRaceState(self):
        time1 = randint(90000, 95000) / 1000.0
        time2 = randint(90000, 95000) / 1000.0
        flag = FlagStatus(randint(0, 6)).name.lower()
        return {
            "cars": [
                ["7", "DriverName", 7, 0, 0, time1, 1],
                ["8", "Driver Two", 7, 0.123, 0.123, time2, 1]
            ],
            "session": {
                "flagState": flag,
                "timeElapsed": 0,
                "timeRemain": 0
            }
        }

    def _getMessageGenerators(self):
        return [
            FlagChangeMessage(),
            CarPitMessage(self.getColumnSpec()),
            DriverChangeMessage(self.getColumnSpec()),
            FastLapMessage(self.getColumnSpec()),
        ]

    def getExtraMessageGenerators(self):
        return []

    def createMessages(self, oldState, newState):
        # Messages are of the form [time, category, text, messageType]
        messages = []
        for mg in self._getMessageGenerators() + self.getExtraMessageGenerators():
            messages += mg.process(oldState, newState)
        return messages

    def getTimingMessage(self):
        return self.state

    def requestCurrentState(self):
        return Message(MessageClass.SERVICE_DATA, self.getTimingMessage()).serialise()

    def publishManifest(self):
        self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.createServiceRegistration()).serialise())

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready for service {}".format(self.uuid))
        yield self.register(self.isAlive, RPC.LIVENESS_CHECK.format(self.uuid))
        yield self.register(self.requestCurrentState, RPC.REQUEST_STATE.format(self.uuid))
        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.info("Subscribed to control channel")
        yield self.publishManifest()
        self.log.info("Published init message")

        while True:
            self.log.info("Publishing timing data for {}".format(self.uuid))
            self._updateRaceState()
            self.publish(unicode(self.uuid), Message(MessageClass.SERVICE_DATA, self.getTimingMessage()).serialise())
            yield sleep(self.getPollInterval())

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.info("Received message {}".format(msg))
        if msg.msgClass == MessageClass.INITIALISE_DIRECTORY:
            yield self.publishManifest()

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


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
                self.callback(feed.read())
            except:
                pass  # Bad data feed :(
            time.sleep(self.interval)


def JSONFetcher(url, callback, interval):
    return Fetcher(url, lambda j: callback(simplejson.loads(j)), interval)


def MultiLineFetcher(url, callback, interval):
    return Fetcher(url, lambda l: callback(l.splitlines()), interval)


def parse_args():
    parser = argparse.ArgumentParser(description='Run a Live Timing service.')

    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('-r', '--recording-file', nargs='?', help='File to record timing data to')
    parser.add_argument('-d', '--description', nargs='?', help='Service description')
    parser.add_argument('service_class', nargs='?', default='livetiming.service.Service', help='Class name of service to run')
    parser.add_argument('-v', '--verbose', action='store_true')

    return parser.parse_known_args()


def get_class(kls):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__(module)
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


def service_name_from(srv):
    if srv.startswith("livetiming."):
        return srv
    return "livetiming.{}.Service".format(srv)


def main():
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))

    args, extra_args = parse_args()

    extra = vars(args)
    extra['extra_args'] = extra_args

    service_class = get_class(service_name_from(args.service_class))
    Logger().info("Starting timing service {}...".format(service_class.__module__))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING, extra=extra)

    with open("{}.log".format(args.service_class), 'a', 0) as logFile:
        if not args.verbose:
            txaio.start_logging(out=logFile, level='info')
        runner.run(service_class)
        print "Service terminated."

if __name__ == '__main__':
    main()
