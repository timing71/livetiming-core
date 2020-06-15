from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from twisted.internet import reactor

try:
    import upnpy
except ModuleNotFoundError:
    upnpy = None

import os
import simplejson
import socket
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

            if should_use_upnp and upnpy:
                try:
                    upnp_forwarded_port, uservice = self.upnp_forward_port(actual_port)
                except Exception:
                    self.service.log.failure(
                        'UPnP forwarding failed! Manually forward port {port} on'
                        ' your router to make the data externally accessible.',
                        port=actual_port
                    )
            elif should_use_upnp:
                self.service.log.warn(
                    'UPnP port forwarding requested but upnpy is not'
                    ' available. Please manually configure port forwarding.'
                )

        txaio.start_logging()
        reactor.run()

        if upnp_forwarded_port and uservice:
            uservice.DeletePortMapping(
                NewRemoteHost='',
                NewProtocol='TCP',
                NewExternalPort=upnp_forwarded_port
            )
            self.service.log.info('Removed UPnP port forward for port {port}', port=upnp_forwarded_port)

    def upnp_forward_port(self, port):
        u = upnpy.UPnP()
        devices = u.discover()

        if len(devices) > 0:
            igd = u.get_igd()

            for uservice in igd.get_services():
                if uservice.type_ == 'WANIPConnection':
                    ext_ip = uservice.GetExternalIPAddress()['NewExternalIPAddress']
                    int_ip = get_local_ip()
                    external_port, needs_creating = find_nearest_free_port(port, uservice, int_ip)

                    if needs_creating:
                        uservice.AddPortMapping(
                            NewRemoteHost='',
                            NewExternalPort=external_port,
                            NewProtocol='TCP',
                            NewInternalPort=port,
                            NewInternalClient=int_ip,
                            NewEnabled=1,
                            NewPortMappingDescription='Timing71 standalone service port forward',
                            NewLeaseDuration=0
                        )
                    else:
                        self.service.log.info('Reusing exising UPnP port forwarding')

                    self.service.log.info(
                        '*** This service is accessible at {host} port {port} ***',
                        host=ext_ip,
                        port=external_port
                    )

                    return external_port, uservice
            raise Exception('Unable to find a UPnP service to configure port forwarding')

        else:
            self.service.log.warn('UPnP forwarding requested but no UPnP router found!')


def find_nearest_free_port(port, uservice, int_ip):
    eport = port
    needs_creating = True

    r = get_tcp_mapping_for_port(eport, uservice)
    while r is not None and eport < 65536:
        if r['NewInternalClient'] == int_ip:
            # We've discovered a stale UPnP forward from a previous incarnation
            # Let's reuse it
            needs_creating = False
            break
        eport = eport + 1
        r = get_tcp_mapping_for_port(eport, uservice)
    return eport, needs_creating


def get_tcp_mapping_for_port(port, uservice):
    try:
        return uservice.GetSpecificPortMappingEntry(
            NewProtocol='TCP',
            NewRemoteHost='',
            NewExternalPort=port
        )
    except Exception:
        return None


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    my_ip = s.getsockname()[0]
    s.close()
    return my_ip
