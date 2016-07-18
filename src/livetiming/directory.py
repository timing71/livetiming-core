from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp import auth
from livetiming.network import Channel, Message, MessageClass, Realm, RPC
from os import environ
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger


USER_SECRET = "123456"


class Directory(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.services = {}

    def listServices(self):
        return self.services.values()

    def removeService(self, errorArgs, serviceUUID):
        self.log.info("Removing dead service {}".format(serviceUUID))
        self.services.pop(serviceUUID)
        self.broadcastServicesList()

    def checkLiveness(self):
        self.log.info("Checking liveness of {} service(s)".format(len(self.services)))
        for service in self.services.keys():
            _ = self.call(RPC.LIVENESS_CHECK.format(service)).addErrback(self.removeService, serviceUUID=service)

    def broadcastServicesList(self):
        self.publish(Channel.CONTROL, Message(MessageClass.DIRECTORY_LISTING, self.services.values()).serialise())

    def onConnect(self):
        print("Client session connected. Starting WAMP-CRA authentication on realm '{}' as user '{}' ..".format(self.config.realm, "directory"))
        self.join(self.config.realm, [u"wampcra"], "hans")

    def onChallenge(self, challenge):
        if challenge.method == u"wampcra":
            print("WAMP-CRA challenge received: {}".format(challenge))

            if u'salt' in challenge.extra:
                # salted secret
                key = auth.derive_key(USER_SECRET,
                                      challenge.extra['salt'],
                                      challenge.extra['iterations'],
                                      challenge.extra['keylen'])
            else:
                # plain, unsalted secret
                key = USER_SECRET

            # compute signature for challenge, using the key
            signature = auth.compute_wcs(key, challenge.extra['challenge'])

            # return the signature to the router for verification
            return signature

        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.debug("Subscribed to control channel")
        yield self.publish(Channel.CONTROL, Message(MessageClass.INITIALISE_DIRECTORY).serialise())
        self.log.debug("Published init message")
        yield self.register(self.listServices, RPC.DIRECTORY_LISTING)
        self.log.debug("Registered service listing RPC")

        liveness = task.LoopingCall(self.checkLiveness)
        liveness.start(10)

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.info("Received message {}".format(msg))
        if (msg.msgClass == MessageClass.SERVICE_REGISTRATION):
            reg = msg.payload
            self.services[reg["uuid"]] = reg
            self.broadcastServicesList()

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
