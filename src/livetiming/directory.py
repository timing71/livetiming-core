from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.messaging import Channel, Message, MessageClass, Realm
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ConnectionRefusedError
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
        yield self.register(self.listServices, u"livetiming.directory.listServices")
        self.log.debug("Registered service listing RPC")

    def onControlMessage(self, message):
        self.log.info("Received message {}".format(Message.parse(message)))

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    Logger().info("Starting directory service...")
    while True:
        try:
            runner = ApplicationRunner(url=u"ws://localhost:5080/ws", realm=Realm.TIMING)
            runner.run(Directory)
        except ConnectionRefusedError:
            pass


if __name__ == '__main__':
    main()
