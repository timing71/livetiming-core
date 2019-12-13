from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

import simplejson
import txaio


class StandaloneSession(object):
    def __init__(self, protocol, port_callback=None):
        self._protocol = protocol
        self._port_callback = port_callback

    def run(self):
        factory = WebSocketServerFactory()
        factory.protocol = self._protocol

        listening_port = reactor.listenTCP(0, factory)
        if self._port_callback:
            self._port_callback(listening_port.getHost().port)

        txaio.start_logging()
        reactor.run()


def create_standalone_session(service, port_callback=None):
    class StandaloneServiceProtocol(WebSocketServerProtocol):

        def onConnect(self, request):
            service.set_publish(self.publish)
            service.publishManifest()

        def onClose(self, wasClean, code, reason):
            service.set_publish(None)

        def publish(self, channel, message, *args, **kwargs):
            payload = simplejson.dumps([
                channel,
                message
            ])
            self.sendMessage(payload.encode('utf-8'), False)

    return StandaloneSession(StandaloneServiceProtocol, port_callback)
