from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.messaging import Channel, Message, MessageClass, Realm, RPC
from os import environ
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger


class Directory(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.services = {}

    def listServices(self):
        return self.services.values()

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.debug("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        self.log.debug("Published init message")
        yield self.register(self.listServices, RPC.DIRECTORY_LISTING)
        self.log.debug("Registered service listing RPC")

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.info("Received message {}".format(msg))
        if (msg.msgClass == MessageClass.SERVICE_REGISTRATION):
            reg = msg.payload
            if reg["uuid"] not in self.services.keys():
                self.services[reg["uuid"]] = reg

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    Logger().info("Starting directory service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(Directory)


if __name__ == '__main__':
    main()
