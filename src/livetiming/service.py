from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.twisted.util import sleep
from livetiming.messages import FlagChangeMessage
from livetiming.network import Channel, Message, MessageClass, Realm, RPC
from os import environ, path
from random import randint
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from uuid import uuid4
from livetiming.racing import FlagStatus
import argparse
import simplejson


class Service(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.args = config.extra
        self.uuid = path.splitext(self.args["initial_state"])[0] if self.args["initial_state"] is not None else uuid4().hex
        self.state = self.getInitialState()

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

    def createServiceRegistration(self):
        return {
            "uuid": self.uuid,
            "name": self.getName(),
            "description": self.getDescription(),
            "colSpec": self.getColumnSpec(),
            "trackDataSpec": self.getTrackDataSpec()
        }

    def getName(self):
        return "Generic Service"

    def getDescription(self):
        return "A generic service that has no purpose other than as a base class"

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("Driver", "text"),
            ("Laps", "numeric"),
            ("Gap", "time"),
            ("Int", "time"),
            ("Last", "time"),
            ("Pits", "numeric")
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
            self.state["cars"] = newState["cars"]
            self.state["session"] = newState["session"]
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

    def getMessageGenerators(self):
        return [
            FlagChangeMessage(lambda s: FlagStatus.fromString(s["session"]["flagState"]))
        ]

    def createMessages(self, oldState, newState):
        # Messages are of the form [time, category, text, messageType]
        messages = []
        for mg in self.getMessageGenerators():
            messages += mg.process(oldState, newState)
        return messages

    def getTimingMessage(self):
        return self.state

    def requestCurrentState(self):
        return Message(MessageClass.SERVICE_DATA, self.getTimingMessage()).serialise()

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready for service {}".format(self.uuid))
        yield self.register(self.isAlive, RPC.LIVENESS_CHECK.format(self.uuid))
        yield self.register(self.requestCurrentState, RPC.REQUEST_STATE.format(self.uuid))
        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.info("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.createServiceRegistration()).serialise())
        self.log.info("Published init message")

        # Update race state (randomly) every 10 seconds
        updater = task.LoopingCall(self._updateRaceState)
        updater.start(self.getPollInterval())

        while True:
            self.log.info("Publishing timing data for {}".format(self.uuid))
            self.publish(unicode(self.uuid), Message(MessageClass.SERVICE_DATA, self.getTimingMessage()).serialise())
            yield sleep(self.getPollInterval())  # No point in sleeping for less time than we wait between updates!

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.info("Received message {}".format(msg))
        if msg.msgClass == MessageClass.INITIALISE_DIRECTORY:
            yield self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.createServiceRegistration()).serialise())

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def parse_args():
    parser = argparse.ArgumentParser(description='Run a Live Timing service.')

    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('service_class', nargs='?', default='livetiming.service.Service', help='Class name of service to run')

    return parser.parse_args()


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

    args = parse_args()

    service_class = get_class(service_name_from(args.service_class))
    Logger().info("Starting timing service {}...".format(service_class.__module__))

    runner = ApplicationRunner(url=router, realm=Realm.TIMING, extra=vars(args))
    runner.run(service_class)

if __name__ == '__main__':
    main()
