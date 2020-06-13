from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

import os
import simplejson
import txaio


class BroadcastServerFactory(WebSocketServerFactory):
    def __init__(self):
        WebSocketServerFactory.__init__(self)
        self.clients = []

    def register(self, client):
        if client not in self.clients:
            self.clients.append(client)

    def unregister(self, client):
        if client in self.clients:
            self.clients.remove(client)

    def publish(self, channel, message, *args, **kwargs):
        payload = simplejson.dumps([
            channel,
            message
        ]).encode('utf-8')

        preparedMsg = self.prepareMessage(payload)
        for c in self.clients:
            c.sendPreparedMessage(preparedMsg)


def make_protocol(service):
    class StandaloneServiceProtocol(WebSocketServerProtocol):

        def onOpen(self):
            self.factory.register(self)
            service.log.info(
                'Client {peer} connected (total={total})',
                peer=self.peer,
                total=len(self.factory.clients)
            )
            service.publishManifest()
            service._publishRaceState()
            if service.analyser:
                service.analyser.publish_all()

        def connectionLost(self, reason):
            WebSocketServerProtocol.connectionLost(self, reason)
            self.factory.unregister(self)
            service.log.info(
                'Client {peer} disconnected (remaining={remaining})',
                peer=self.peer,
                remaining=len(self.factory.clients)
            )

    return StandaloneServiceProtocol


class StandaloneSession(object):
    def __init__(self, service, port_callback=None):
        self._protocol = make_protocol(service)
        self._port_callback = port_callback
        self.service = service

    def run(self):
        factory = BroadcastServerFactory()
        factory.protocol = self._protocol
        self.service.set_publish(factory.publish)

        port = int(os.environ.get('LIVETIMING_STANDALONE_PORT', 0))

        listening_port = reactor.listenTCP(port, factory)
        if self._port_callback:
            self._port_callback(listening_port.getHost().port)

        txaio.start_logging()
        reactor.run()
