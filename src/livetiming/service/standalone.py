from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

try:
    import miniupnpc
except ModuleNotFoundError:
    miniupnpc = None

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
    def __init__(self, service, port_callback=None, use_upnp=False):
        self._protocol = make_protocol(service)
        self._port_callback = port_callback
        self.service = service
        self.use_upnp = use_upnp

    def run(self):
        factory = BroadcastServerFactory()
        factory.protocol = self._protocol
        self.service.set_publish(factory.publish)

        port = int(os.environ.get('LIVETIMING_STANDALONE_PORT', 0))

        listening_port = reactor.listenTCP(port, factory)
        actual_port = listening_port.getHost().port

        upnp_forwarded_port, upnp = None, None

        if self._port_callback:
            self._port_callback(actual_port)

            should_use_upnp = self.use_upnp or os.environ.get('LIVETIMING_USE_UPNP', False)

            if should_use_upnp and miniupnpc:
                try:
                    upnp_forwarded_port, upnp = self.upnp_forward_port(actual_port)
                except Exception:
                    self.service.log.failure(
                        'UPnP forwarding failed! Manually forward port {port} on'
                        ' your router to make the data externally accessible.',
                        port=actual_port
                    )
            elif should_use_upnp:
                self.service.log.warn(
                    'UPnP port forwarding requested but miniupnpc is not'
                    ' available. Please manually configure port forwarding.'
                )

        txaio.start_logging()
        reactor.run()

        if upnp_forwarded_port and upnp:
            upnp.deleteportmapping(upnp_forwarded_port, 'TCP')
            self.service.log.info('Removed UPnP port forward for port {port}', port=upnp_forwarded_port)

    def upnp_forward_port(self, port):
        u = miniupnpc.UPnP()
        num_devices = u.discover()

        if num_devices > 0:
            igd = u.selectigd()
            external_port = find_nearest_free_port(port, u)

            b = u.addportmapping(
                external_port,
                'TCP',
                u.lanaddr,
                port,
                'Timing71 standalone service port forward',
                ''
            )
            if b:
                self.service.log.info(
                    '*** This service is accessible at {host} port {port} ***',
                    host=u.externalipaddress(),
                    port=external_port
                )

            return external_port, u

        else:
            self.service.log.warn('UPnP forwarding requested but no UPnP router found!')


def find_nearest_free_port(port, upnp):
    eport = port
    r = upnp.getspecificportmapping(eport, 'TCP')
    while r is not None and eport < 65536:
        eport = eport + 1
        r = u.getspecificportmapping(eport, 'TCP')
    return eport
