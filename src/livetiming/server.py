from autobahn.twisted.util import sleep
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from twisted.internet.defer import inlineCallbacks


class MyComponent(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):
        print("session ready")

        counter = 0
        while True:
            self.publish(u'com.myapp.oncounter', counter)
            counter += 1
            yield sleep(1)


def main():
    print "Starting..."
    runner = ApplicationRunner(url=u"ws://crossbar:8080/ws", realm=u"timing")
    runner.run(MyComponent)


if __name__ == '__main__':
    main()
