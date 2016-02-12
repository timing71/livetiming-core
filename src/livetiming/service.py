from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.twisted.util import sleep
from livetiming.messaging import Channel, Message, MessageClass, Realm, RPC
from os import environ
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from uuid import uuid4


class Service(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.uuid = uuid4().hex

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
            ("Num", "numeric"),
            ("Driver", "text"),
            ("Laps", "numeric"),
            ("Gap", "time"),
            ("Int", "time"),
            ("Last", "time"),
            ("Pits", "time")
        ]

    def isAlive(self):
        return True

    def getTimingMessage(self):
        return {
            "cars": [
                ["7", "DriverName", 7, 0, 0, 92.546, 1],
                ["8", "Driver Two", 7, 0.123, 0.123, 91.946, 1]
            ]
        }

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready for service {}".format(self.uuid))
        yield self.register(self.isAlive, RPC.LIVENESS_CHECK.format(self.uuid))
        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.info("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.createServiceRegistration()).serialise())
        self.log.info("Published init message")
        while True:
            self.log.info("Publishing timing data for {}".format(self.uuid))
            self.publish(unicode(self.uuid), Message(MessageClass.SERVICE_DATA, self.getTimingMessage()).serialise())
            yield sleep(1)

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
