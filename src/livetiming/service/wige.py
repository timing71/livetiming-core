# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.messages import TimingMessage
from livetiming.nurburgring_utils import Nurburgring
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import copy
import simplejson
import time


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


def mapState(raw, ontrack):
    states = {
        '0': 'N/S',
        '1': 'RUN',
        '2': 'RUN',
        '3': 'RUN',
        '4': 'RUN',
        '5': 'RUN',
        '6': 'RUN',
        '7': 'PIT',
        '8': 'PIT',
        '9': 'OUT',
        '10': 'RUN',  # This and below are guesses
        '11': 'RUN',
        '14': 'PIT'
    }
    if not ontrack:
        return 'PIT'
    if raw in states:
        return states[raw]
    print "Unknown state: {}".format(raw)
    return "? {}".format(raw)


def mapCar(car):
    return [
        car['STNR'],
        mapState(car['LASTINTERMEDIATENUMBER'], car.get('ONTRACK', True)),
        # car['LASTINTERMEDIATENUMBER'],
        car['CLASSNAME'],
        car['CLASSRANK'],
        car['NAME'],
        car['TEAM'],
        car['CAR'],
        parseGap(car['GAP']),
        parseGap(car['INT']),
        (parseTime(car.get('S1TIME', '')), ''),
        (parseTime(car.get('S2TIME', '')), ''),
        (parseTime(car.get('S3TIME', '')), ''),
        (parseTime(car.get('S4TIME', '')), ''),
        (parseTime(car.get('S5TIME', '')), ''),
        (parseTime(car['LASTLAPTIME']), ''),
        (parseTime(car['FASTESTLAP']), ''),
        car['PITSTOPCOUNT']
    ]


def postprocess_cars(cars):
    fastest = (None, None)
    for car in cars:
        race_num = car[0]
        last = car[14]
        best = car[15]

        if last[0] == best[0]:
            car[14] = (last[0], 'pb')
        if not fastest[0] or best[0] < fastest[0]:
            fastest = (best[0], race_num)

    for car in cars:
        race_num = car[0]
        last = car[14]
        best = car[15]
        s5 = car[13]

        if race_num == fastest[1]:
            car[15] = (best[0], 'sb')
            if last[0] == best[0] and s5[0] != '':
                car[14] = (last[0], 'sb-new')

    return cars


class SlowZoneMessage(TimingMessage):
    def __init__(self, prevZones, currentZones):
        self._prev = prevZones
        self._curr = currentZones

    def process(self, oldState, newState):
        msgs = []

        for zone, state in self._curr.iteritems():
            severity, mp, location = state
            if zone not in self._prev:
                if severity == '60':
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "New Code 60 zone at MP{} ({})".format(mp, location),
                        "code60"
                    ])
                elif severity == '120':
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "New slow zone zone at MP{} ({})".format(mp, location),
                        "yellow"
                    ])
            else:
                prev_severity = self._prev[zone][0]
                if prev_severity == '60' and severity == '120':
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "Code 60 zone downgraded to slow at MP{} ({})".format(mp, location),
                        "yellow"
                    ])
                elif prev_severity == '120' and severity == '60':
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "Slow zone upgraded to Code 60 at MP{} ({})".format(mp, location),
                        "code60"
                    ])

        for zone, state in self._prev.iteritems():
            if zone not in self._curr:
                severity, mp, location = state
                msgs.append([
                    int(time.time()),
                    "Track",
                    "Track clear at MP{} ({})".format(mp, location),
                    "green"
                ])

        return msgs


class Service(lt_service):
    attribution = ['wige', 'http://www.wige-livetiming.de']
    auto_poll = False

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._data = {}
        self._nbr = Nurburgring()
        self._current_zones = {}
        self._last_zones = {}

        self.log.info("Using WebSocket URL {url}", url=self._extra.ws)
        self._connectWS(self._extra.ws, self._extra.event_id)

    def _connectWS(self, url, event_id):
            factory = ReconnectingWebSocketClientFactory(url)
            factory.protocol = create_ws_protocol(self.log, self.handle, event_id)
            connectWS(factory)

    def handle(self, data):
        needs_republish = False
        if data.get('CUP', None) != self._data.get('CUP'):
            needs_republish = True
        if data.get('HEAT', None) != self._data.get('HEAT'):
            needs_republish = True

        self._data = data

        if needs_republish:
            self.analyser.reset()
            self.publishManifest()
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

    def getTrackDataSpec(self):
        return [
            'Slow zones',
            'Code 60 zones'
        ]

    def getExtraMessageGenerators(self):
        return [
            SlowZoneMessage(self._current_zones, self._last_zones)
        ]

    def getRaceState(self):
        self._last_zones.clear()
        self._last_zones.update(self._current_zones)
        self._current_zones.clear()
        self._current_zones.update(self._nbr.active_zones())

        slow_zones = 0
        code60_zones = 0
        for z in self._current_zones:
            speed = z[0]
            if z[0] == '60':
                code60_zones += 1
            elif z[0] == '120':
                slow_zones += 1

        if 'TRACKSTATE' in self._data and self._data['TRACKSTATE'] == "0":
            flag = FlagStatus.NONE
        elif code60_zones > 0:
            flag = FlagStatus.CODE_60_ZONE
        elif slow_zones > 0:
            flag = FlagStatus.SLOW_ZONE
        else:
            flag = FlagStatus.GREEN

        return {
            'cars': postprocess_cars(map(mapCar, self._data.get('RESULT', {}))),
            'session': {
                "flagState": flag.name.lower(),
                "timeElapsed": 0,
                'trackData': [
                    slow_zones,
                    code60_zones
                ]
            }
        }
