from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

import simplejson


class StandaloneSession(object):
    def __init__(self, protocol):
        self._protocol = protocol

    def run(self):
        factory = WebSocketServerFactory()
        factory.protocol = self._protocol

        reactor.listenTCP(9000, factory)
        reactor.run()


def create_standalone_session(service):
    class StandaloneServiceProtocol(WebSocketServerProtocol):

        def onConnect(self, request):
            service.set_publish(self.publish)

        def onClose(self, wasClean, code, reason):
            service.set_publish(None)

        def publish(self, channel, message, *args, **kwargs):
            payload = simplejson.dumps([
                channel,
                message
            ])
            self.sendMessage(payload.encode('utf-8'), False)

    return StandaloneSession(StandaloneServiceProtocol)
