from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import re
import time
import xml.etree.ElementTree as ET


def create_ws_protocol(log, handler):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            log.info('Connected to upstream timing source')
            self.factory.resetDelay()

        def onMessage(self, payload, isBinary):
            log.info('Received message: {msg}', msg=payload)

            if payload == '<NotFound />\r\n':
                log.warn('Timing feed not found. Delaying reconnection attempt')
                self.factory.delay = 10  # this is NOT in seconds. It's complicated. This is about 30 seconds' worth.
            else:
                xml_part = payload[payload.index('<'):]
                xml = ET.fromstring(xml_part)
                handler(xml)

    return ClientProtocol


def create_tcp_protocol(log, handler):

    header_regex = re.compile('^!@#(?P<len>[0-9]{5})(?P<cont>..)(?:<)')

    class TCPProtocol(Protocol, object):
        def __init__(self):
            super(TCPProtocol, self).__init__()
            self._buffer = ""
            self._cont_stack = []

        def connectionMade(self):
            log.info('Connected to upstream timing source')

        def dataReceived(self, payload):
            log.debug('Received message: {msg}', msg=payload)

            self._buffer += payload

            buffer_header = header_regex.match(self._buffer)
            header_len = int(buffer_header.group('len')) if buffer_header else -1

            while buffer_header and len(self._buffer) >= header_len:
                log.debug("Buffer header says length is {hlen}, buffer is {blen}", hlen=header_len, blen=len(self._buffer))
                message = self._buffer[10:header_len + 10]

                cont_header = buffer_header.group('cont')
                if cont_header[1] != '=':
                    # This is part of a continuation
                    self._cont_stack.append(message)
                elif cont_header[0] != '=':
                    # This is the end of the continuation
                    self._cont_stack.append(message)
                    message = ''.join(self._cont_stack)
                    log.debug("Processing message: '{msg}'", msg=message)
                    handler(ET.fromstring(message))
                    self._cont_stack = []
                else:
                    log.debug("Processing message: '{msg}'", msg=message)
                    handler(ET.fromstring(message))

                self._buffer = self._buffer[header_len + 10:]
                log.debug("New buffer is {buf}", buf=self._buffer)
                buffer_header = header_regex.match(self._buffer)
                header_len = int(buffer_header.group('len')) if buffer_header else -1

    return TCPProtocol


class NatsoftState(object):

    HANDLERS = {
        'New': 'new'
    }

    def __init__(self, logger):
        self.log = logger
        self._reset()

    def _reset(self):
        self._categories = {}
        self._positions = {}
        self._session = {}
        self._competitors = {}

    def handle(self, xml):
        if xml.tag in self.HANDLERS:
            handler_name = "handle_{}".format(self.HANDLERS[xml.tag])
            self.log.debug("Invoking handler {handler_name}", handler_name=handler_name)
            getattr(self, handler_name)(xml)
        else:
            self.log.warn("Unhandled XML tag: {tag}", tag=xml.tag)

    def handle_new(self, xml):
        pass


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--url', help='WebSocket URL to connect to')
    parser.add_argument('--host', help='Host to connect to for a TCP connection')
    parser.add_argument('-p', '--port', help='Port to connect to for a TCP connection', type=int)
    parser.add_argument('-n', '--name', help='Service name', default='Natsoft timing feed')

    return parser.parse_args(extra_args)


class Service(lt_service):
    attribution = ['Natsoft', 'http://racing.natsoft.com.au']

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._has_session = False

        self._state = NatsoftState(self.log)

        if self._extra.url:
            factory = ReconnectingWebSocketClientFactory(self._extra.url)
            factory.protocol = create_ws_protocol(self.log, self._state.handle)
            connectWS(factory)
        elif self._extra.host and self._extra.port:
            factory = ReconnectingClientFactory()
            factory.protocol = create_tcp_protocol(self.log, self._state.handle)
            reactor.connectTCP(self._extra.host, self._extra.port, factory)
        else:
            raise Exception("Either websocket URL or host/port must be specified")

    def getName(self):
        return self._extra.name

    def getDefaultDescription(self):
        return ''

    def getColumnSpec(self):
        return [
        ]

    def getRaceState(self):
        if not self._has_session:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0
                }
            }
        return {
            'cars': [],
            'session': {}
        }
