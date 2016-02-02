from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.messaging import Channel, Message, MessageClass, Realm
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ConnectionRefusedError
from twisted.logger import Logger


class Directory(ApplicationSession):
    log = Logger()

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.debug("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        self.log.debug("Published init message")

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
            runner = ApplicationRunner(url=u"ws://crossbar:8080/ws", realm=Realm.TIMING)
            runner.run(Directory)
        except ConnectionRefusedError:
            pass


if __name__ == '__main__':
    main()
