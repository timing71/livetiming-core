# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.messages import TimingMessage, CAR_NUMBER_REGEX
from livetiming.utils.nurburgring import Nurburgring
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
            self.sendMessage('{"eventId": "' + eventID + '","eventPid":[0,3,4]}')

        def onMessage(self, payload, isBinary):
            log.debug('Received message: {msg}', msg=payload)

            handler(simplejson.loads(payload))

    return ClientProtocol


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', '--ws', help='WebSocket URL to connect to', default='wss://livetiming.azurewebsites.net')
    parser.add_argument('-e', '--event-id', help='Event ID', required=True)
    parser.add_argument('--nurburgring', help='Use Nurburgring-specific features', action='store_true')
    parser.add_argument('--gpsauge', help='GPSauge app ID to use for Nbr features')

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
        return '{} laps'.format(laps) if laps > 1 else '1 lap'
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
        '7': 'RUN',
        '8': 'RUN',
        '9': 'RUN',
        '10': 'RUN',  # This and below are guesses
        '11': 'RUN',
        '12': 'RUN',
        '14': 'PIT',
        '15': 'OUT',
        '16': 'RUN',
        '20': 'RUN'
    }
    if not ontrack:
        return 'PIT'
    if raw in states:
        return states[raw]
    print "Unknown state: {}".format(raw)
    return "? {}".format(raw)


class SlowZoneMessage(TimingMessage):
    def __init__(self, prevZones, currentZones):
        self._prev = prevZones
        self._curr = currentZones

    def process(self, oldState, newState):
        msgs = []

        for zone, state in self._curr.iteritems():
            severity, mp, location = state
            if zone not in self._prev:
                if severity == 0:
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "Yellow flag at MP{} ({})".format(mp, location),
                        "yellow"
                    ])
                if severity == 60:
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "New Code 60 zone at MP{} ({})".format(mp, location),
                        "code60"
                    ])
                elif severity == 120:
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "New slow zone at MP{} ({})".format(mp, location),
                        "yellow"
                    ])
            else:
                prev_severity = self._prev[zone][0]
                if prev_severity == 60 and severity == 120:
                    msgs.append([
                        int(time.time()),
                        "Track",
                        "Code 60 zone downgraded to slow at MP{} ({})".format(mp, location),
                        "yellow"
                    ])
                elif prev_severity == 120 and severity == 60:
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


class RaceControlMessage(TimingMessage):
    def __init__(self, messages):
        self._messages = messages
        self._mostRecentTime = 0

    def process(self, _, __):
        # current = rcm.get('currentMessages', {})
        # for idx, msg in current.iteritems():
        #     if self._seen_current_msgs.get(idx) != msg['message']:
        #         new_messages.append(msg)
        #         self._seen_current_msgs[idx] = msg['message']

        msgs = []

        for msg in self._messages:
            hasCarNum = CAR_NUMBER_REGEX.search(msg['MESSAGE'])

            this_msg_time = datetime.now()
            msgTime = msg.get('MESSAGETIME')
            if msgTime:
                parsed_msgtime = datetime.strptime(msgTime, "%H:%M:%S")
                this_msg_time = this_msg_time.replace(
                    hour=parsed_msgtime.hour - 1 if parsed_msgtime.hour > 1 else 23,
                    minute=parsed_msgtime.minute,
                    second=parsed_msgtime.second
                )

            this_msg_timestamp = time.mktime(this_msg_time.timetuple())

            if this_msg_timestamp > self._mostRecentTime:

                if hasCarNum:
                    msgs.append([this_msg_timestamp, "Race Control", msg['MESSAGE'].upper(), "raceControl", hasCarNum.group('race_num')])
                else:
                    msgs.append([this_msg_timestamp, "Race Control", msg['MESSAGE'].upper(), "raceControl"])

            if len(msgs) > 0:
                self._mostRecentTime = max(max(self._mostRecentTime, map(lambda m: m[0], msgs)))
        return sorted(msgs, key=lambda m: -m[0])


class Service(lt_service):
    attribution = ['wige Solutions']
    auto_poll = False

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)
        self._messages = []
        self._rc_messages = RaceControlMessage(self._messages)

        self._data = {}

        if self._extra.nurburgring:
            self._nbr = Nurburgring(self._extra.gpsauge)
            self._current_zones = {}
            self._last_zones = {}

        self.log.info("Using WebSocket URL {url}", url=self._extra.ws)
        self._connectWS(self._extra.ws, self._extra.event_id)

    def _connectWS(self, url, event_id):
            factory = ReconnectingWebSocketClientFactory(url)
            factory.protocol = create_ws_protocol(self.log, self.handle, event_id)
            connectWS(factory)

    def handle(self, data):

        if data.get('PID') == "0":  # Timing data
            needs_republish = False
            if data.get('CUP', None) != self._data.get('CUP', None):
                needs_republish = True
            if data.get('HEAT', None) != self._data.get('HEAT', None):
                needs_republish = True

            self._data = data

            if needs_republish:
                self.publishManifest()
            self._updateAndPublishRaceState()
        elif data.get('PID') == "3":  # Messages
            self._messages = data.get('MESSAGES', [])
            self._rc_messages._messages = self._messages
        else:
            self.log.warn(u'Received message with unknown PID: {msg}', msg=data)

    def getName(self):
        return self._data.get('CUP', 'wige Solutions')

    def getDefaultDescription(self):
        return u'{} - {}'.format(
            self._data.get('HEAT', ''),
            self._data.get('TRACKNAME', '')
        )

    def getPollInterval(self):
        return None

    def getColumnSpec(self):

        num_sectors = int(self._data.get('NROFINTERMEDIATETIMES', 4)) + 1
        sector_cols = map(lambda s: Stat.sector(s + 1), range(num_sectors))

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
            Stat.INT
        ] + sector_cols + [
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getTrackDataSpec(self):
        if self._extra.nurburgring:
            return [
                'Slow zones',
                'At',
                'Code 60 zones',
                'At'
            ]
        return []

    def getExtraMessageGenerators(self):
        if self._extra.nurburgring:
            return [
                SlowZoneMessage(self._last_zones, self._current_zones),
                self._rc_messages
            ]
        return [self._rc_messages]

    def getRaceState(self):
        if self._extra.nurburgring:
            self._last_zones.clear()
            self._last_zones.update(self._current_zones)
            self._current_zones.clear()
            self._current_zones.update(self._nbr.active_zones())

            yellows = 0
            slow_zones = 0
            code60_zones = 0

            sz_locations = set()
            c60_locations = set()

            for z in sorted(self._current_zones.values(), key=lambda z: z[1]):
                speed = z[0]
                if speed == 0:
                    yellows += 1
                if speed == 60:
                    code60_zones += 1
                    c60_locations.add(z[2])
                elif speed == 120:
                    slow_zones += 1
                    sz_locations.add(z[2])

            if len(self._current_zones) == 209 and self._current_zones.values()[0][0] == 80:
                flag = FlagStatus.RED
            elif code60_zones > 0:
                flag = FlagStatus.CODE_60_ZONE
            elif slow_zones > 0:
                flag = FlagStatus.SLOW_ZONE
            elif yellows > 0:
                flag = FlagStatus.YELLOW
            elif 'TRACKSTATE' in self._data:
                ts = self._data['TRACKSTATE']
                if ts == "0":
                    flag = FlagStatus.GREEN
                elif ts == "1":
                    flag = FlagStatus.YELLOW
                elif ts == "2":
                    flag = FlagStatus.RED
            else:
                flag = FlagStatus.GREEN

            track_data = [
                slow_zones,
                ', '.join(sz_locations),
                code60_zones,
                ', '.join(c60_locations)
            ]
        else:
            flag = FlagStatus.NONE
            track_data = []

        return {
            'cars': self.postprocess_cars(map(self.map_car, self._data.get('RESULT', {}))),
            'session': {
                "flagState": flag.name.lower(),
                "timeElapsed": 0,
                'trackData': track_data
            }
        }

    def map_car(self, car):

        sector_cols = map(
            lambda s: (parseTime(car.get('S{}TIME'.format(s + 1), '')), ''),
            range(int(self._data.get('NROFINTERMEDIATETIMES', 4)) + 1)
        )

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
            parseGap(car['INT'])
        ] + sector_cols + [
            (parseTime(car['LASTLAPTIME']), ''),
            (parseTime(car['FASTESTLAP']), ''),
            car['PITSTOPCOUNT']
        ]

    def postprocess_cars(self, cars):

        colspec = self.getColumnSpec()

        last_lap_idx = colspec.index(Stat.LAST_LAP)
        best_lap_idx = colspec.index(Stat.BEST_LAP)
        last_sector_idx = len(colspec) - 3

        fastest = (None, None)
        for car in cars:
            race_num = car[0]
            last = car[last_lap_idx]
            best = car[best_lap_idx]

            if last[0] == best[0]:
                car[last_lap_idx] = (last[0], 'pb')
            if not fastest[0] or best[0] < fastest[0]:
                fastest = (best[0], race_num)

        for car in cars:
            race_num = car[0]
            last = car[last_lap_idx]
            best = car[best_lap_idx]
            s5 = car[last_sector_idx]

            if race_num == fastest[1]:
                car[best_lap_idx] = (best[0], 'sb')
                if last[0] == best[0] and s5[0] != '':
                    car[last_lap_idx] = (last[0], 'sb-new')

        return cars
