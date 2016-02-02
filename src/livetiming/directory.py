from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.messaging import Channel, Message, MessageClass, Realm
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ConnectionRefusedError
from twisted.logger import Logger


class Directory(ApplicationSession):
    log = Logger()

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.debug("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        self.log.debug("Published init message")
        counter = 0
        while True:
            self.publish(u'com.myapp.oncounter', counter)
            counter += 1
            yield sleep(1)

    def onControlMessage(self, message):
        self.log.info("Received message {}".format(Message.parse(message)))


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
