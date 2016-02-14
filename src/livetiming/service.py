from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.twisted.util import sleep
from livetiming.messaging import Channel, Message, MessageClass, Realm, RPC
from os import environ
from random import randint
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from uuid import uuid4
from livetiming.racing import FlagStatus


class Service(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.uuid = uuid4().hex
        self.state = {}

    def createServiceRegistration(self):
        return {
            "uuid": self.uuid,
            "name": self.getName(),
            "description": self.getDescription(),
            "colSpec": self.getColumnSpec()
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

    def getPollInterval(self):
        return 10

    def isAlive(self):
        return True

    def _updateRaceState(self):
        newState = self.getRaceState()
        self.state["cars"] = newState["cars"]
        self.state["session"] = newState["session"]

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

    def getTimingMessage(self):
        return self.state

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready for service {}".format(self.uuid))
        yield self.register(self.isAlive, RPC.LIVENESS_CHECK.format(self.uuid))
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


def main():
    Logger().info("Starting generic timing service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(Service)

if __name__ == '__main__':
    main()
