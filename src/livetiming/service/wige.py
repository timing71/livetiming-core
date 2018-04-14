from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import simplejson


def create_ws_protocol(log, handler, eventID):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            log.info('Connected to upstream timing source')
            self.factory.resetDelay()
            self.sendMessage('{"eventId": "' + eventID + '"}')

        def onMessage(self, payload, isBinary):
            log.debug('Received message: {msg}', msg=payload)

            handler(simplejson.loads(payload))

    return ClientProtocol


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--ws', help='WebSocket URL to connect to', required=True)
    parser.add_argument('-e', '--event-id', help='Event ID', required=True)

    return parser.parse_args(extra_args)


def parseDate(raw):
    return datetime.fromtimestamp(raw / 1000)


def parseTime(formattedTime):
    if formattedTime == "" or formattedTime is None:
        return ''
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def parseGap(raw):
    if raw == '':
        return raw
    if raw[0] == 'R':
        laps = int(raw[1:])
        return '{} laps' if laps > 1 else '1 lap'
    if raw[0] == '-':
        return raw[4:].title()
    try:
        secs = float(raw)
        mins, secs = divmod(secs, 60)
        if mins > 0:
            return '{}:{}'.format(mins, secs)
        return secs
    except ValueError:
        return raw


def mapState(raw):
    states = {
        '1': 'RUN',
        '2': 'RUN',
        '3': 'RUN',
        '4': 'RUN',
        '5': 'RUN',
        '6': 'RUN',
        '7': 'PIT',
        '8': 'PIT',
        '9': 'OUT'
    }
    if raw in states:
        return states[raw]
    print "Unknown state: {}".format(raw)
    return '???'


def mapCar(car):
    return [
        car['STNR'],
        mapState(car['LASTINTERMEDIATENUMBER']),
        # car['LASTINTERMEDIATENUMBER'],
        car['CLASSNAME'],
        car['CLASSRANK'],
        car['NAME'],
        car['TEAM'],
        car['CAR'],
        parseGap(car['GAP']),
        parseGap(car['INT']),
        (parseTime(car['S1TIME']), ''),
        (parseTime(car['S2TIME']), ''),
        (parseTime(car['S3TIME']), ''),
        (parseTime(car['S4TIME']), ''),
        (parseTime(car['S5TIME']), ''),
        (parseTime(car['LASTLAPTIME']), ''),
        (parseTime(car['FASTESTLAP']), ''),
        car['PITSTOPCOUNT']
    ]


class Service(lt_service):
    attribution = ['wige', 'http://www.wige-livetiming.de']
    auto_poll = False

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._data = {}

        self.log.info("Using WebSocket URL {url}", url=self._extra.ws)
        self._connectWS(self._extra.ws, self._extra.event_id)

    def _connectWS(self, url, event_id):
            factory = ReconnectingWebSocketClientFactory(url)
            factory.protocol = create_ws_protocol(self.log, self.handle, event_id)
            connectWS(factory)

    def handle(self, data):
        self._data = data
        self._updateAndPublishRaceState()

    def getName(self):
        return "wige Solutions"

    def getDefaultDescription(self):
        return u"{} - {}".format(
            self._data.get('CUP', 'VLN'),
            self._data.get('HEAT', '')
        )

    def getPollInterval(self):
        return None

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            # ('I', 'numeric', 'Last intermediate'),
            Stat.CLASS,
            Stat.POS_IN_CLASS,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.CAR,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.S4,
            Stat.S5,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getRaceState(self):
        return {
            'cars': map(mapCar, self._data.get('RESULT', {})),
            'session': {
                "flagState": "none",
                "timeElapsed": 0,
            }
        }
