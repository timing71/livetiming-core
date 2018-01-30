from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory

import argparse
import time


def create_protocol(service):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            service.log.info('Connected to upstream timing source')
            self.factory.resetDelay()

        def onMessage(self, payload, isBinary):
            service.log.info('Received message: {msg}', msg=payload)

            if payload == '<NotFound />\r\n':
                service.log.warn('Timing feed not found. Delaying reconnection attempt')
                self.factory.delay = 10  # this is NOT in seconds. It's complicated. This is about 30 seconds' worth.

    return ClientProtocol


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--url', help='WebSocket URL to connect to', required=True)
    parser.add_argument('-n', '--name', help='Service name', default='Natsoft timing feed')

    return parser.parse_args(extra_args)


class Service(lt_service):
    attribution = ['Natsoft', 'http://racing.natsoft.com.au']

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._has_session = False

        factory = ReconnectingWebSocketClientFactory(self._extra.url)
        factory.protocol = create_protocol(self)
        connectWS(factory)

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
