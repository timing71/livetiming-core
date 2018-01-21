from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions, PublishOptions
from livetiming import load_env
from livetiming.network import Channel, Message, MessageClass, Realm, RPC, authenticatedService
from os import environ
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger


@authenticatedService
class Directory(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.services = {}
        self.publish_options = PublishOptions(retain=True)

    def removeService(self, errorArgs, serviceUUID):
        self.log.info("Removing dead service {}".format(serviceUUID))
        self.services.pop(serviceUUID)
        self.broadcastServicesList()

    def checkLiveness(self):
        self.log.info("Checking liveness of {} service(s)".format(len(self.services)))
        for service in self.services.keys():
            _ = self.call(RPC.LIVENESS_CHECK.format(service)).addErrback(self.removeService, serviceUUID=service)

    def broadcastServicesList(self):
        self.publish(
            Channel.DIRECTORY,
            Message(MessageClass.DIRECTORY_LISTING, self.services.values()).serialise(),
            options=self.publish_options
        )

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.debug("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        self.log.debug("Published init message")
        self.broadcastServicesList()

        liveness = task.LoopingCall(self.checkLiveness)
        liveness.start(10)

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.debug("Received message {msg}", msg=msg)
        if (msg.msgClass == MessageClass.SERVICE_REGISTRATION):
            reg = msg.payload
            self.services[reg["uuid"]] = reg
            self.broadcastServicesList()

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    load_env()
    Logger().info("Starting directory service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(Directory, auto_reconnect=True)


if __name__ == '__main__':
    main()
