from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.messaging import Channel, Message, MessageClass, Realm
from twisted.internet.defer import inlineCallbacks
from twisted.internet.error import ConnectionRefusedError


class Directory(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):
        print("session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        print "Subscribed"
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        print "Published"
        counter = 0
        while True:
            self.publish(u'com.myapp.oncounter', counter)
            counter += 1
            yield sleep(1)

    def onControlMessage(self, message):
        print "Received message {}".format(Message.parse(message))


def main():
    print "Starting..."
    while True:
        try:
            runner = ApplicationRunner(url=u"ws://crossbar:8080/ws", realm=Realm.TIMING)
            runner.run(Directory)
        except ConnectionRefusedError:
            pass


if __name__ == '__main__':
    main()
