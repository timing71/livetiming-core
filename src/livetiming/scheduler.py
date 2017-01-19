from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.network import Realm, RPC
from os import environ
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger


class Scheduler(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)

    def listSchedule(self):
        return {}  # TODO Stub

    def updateSchedule(self):
        pass  # TODO Stub

    def execute(self):
        pass  # TODO Stub

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.register(self.listSchedule, RPC.SCHEDULE_LISTING)
        self.log.debug("Registered service listing RPC")

        update = task.LoopingCall(self.updateSchedule)
        update.start(600)  # Update from Google Calendar every 10 minutes

        execute = task.LoopingCall(self.execute)
        execute.start(60)  # Start and stop services every minute

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    Logger().info("Starting scheduler service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(Scheduler)


if __name__ == '__main__':
    main()
