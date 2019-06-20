# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.messages import TimingMessage, CAR_NUMBER_REGEX
from livetiming.utils.nurburgring import Nurburgring
from livetiming.service import DuePublisher, Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import copy
import re
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
    parser.add_argument('--tz', help='Adjust timestamps by this many hours', type=int, default=1)

    return parser.parse_args(extra_args)


def parseDate(raw):
    return datetime.fromtimestamp(raw / 1000)


def parseTime(formattedTime):
    if formattedTime == "" or formattedTime is None or formattedTime[0] == '-':
        return ''
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            try:
                ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
                return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
            except ValueError:
                return formattedTime


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
    def __init__(self, messages, tz_adjustment=1):
        self._messages = messages
        self._mostRecentTime = 0
        self._tz_adjustment = tz_adjustment

    def process(self, _, __):
        # current = rcm.get('currentMessages', {})
        # for idx, msg in current.iteritems():
        #     if self._seen_current_msgs.get(idx) != msg['message']:
        #         new_messages.append(msg)
        #         self._seen_current_msgs[idx] = msg['message']

        msgs = []

        for msg in self._messages:
            hasCarNum = CAR_NUMBER_REGEX.search(msg['MESSAGE'])

            this_msg_time = datetime.utcnow()
            msgTime = msg.get('MESSAGETIME')
            if msgTime:
                parsed_msgtime = datetime.strptime(msgTime, "%H:%M:%S")

                new_hour = parsed_msgtime.hour - self._tz_adjustment if parsed_msgtime.hour >= self._tz_adjustment else (24 - parsed_msgtime.hour - self._tz_adjustment)

                this_msg_time = this_msg_time.replace(
                    hour=new_hour,
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


CAR_LAP_REGEX = re.compile('Lap (?P<lap_num>[0-9]+)', re.IGNORECASE)


class Service(DuePublisher, lt_service):
    attribution = ['wige Solutions']
    auto_poll = False

    def __init__(self, args, extra):
        super(Service, self).__init__(args, extra)
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)
        self._messages = []
        self._rc_messages = RaceControlMessage(self._messages, self._extra.tz)

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
            factory.setProtocolOptions(
                openHandshakeTimeout=120
            )
            connectWS(factory, timeout=120)

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
            self.set_due_publish()
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
            Stat.LAPS,
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

        flag = FlagStatus.NONE
        track_data = []

        if 'TRACKSTATE' in self._data:
            ts = self._data['TRACKSTATE']
            if ts == "0":
                flag = FlagStatus.GREEN
            elif ts == "1":
                flag = FlagStatus.YELLOW
            elif ts == "2":
                flag = FlagStatus.RED

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

            track_data = [
                slow_zones,
                ', '.join(sz_locations),
                code60_zones,
                ', '.join(c60_locations)
            ]

        accum = {}

        return {
            'cars': self.postprocess_cars(map(self.map_car(accum), self._data.get('RESULT', {}))),
            'session': {
                "flagState": flag.name.lower(),
                "timeElapsed": 0,
                'trackData': track_data
            }
        }

    def map_car_state(self, raw, ontrack):
        version = self._data.get('VER', '1')
        states = {
            '1': {
                '1': 'RUN',
                '2': 'RUN',
                '3': 'RUN',
                '4': 'RUN',
                '5': 'RUN',
                '6': 'RUN',
                '7': 'RUN',
                '8': 'PIT',
                '9': 'OUT',
                '10': 'RUN',
                '12': 'PIT',
                '14': 'RUN'
            },
            '2': {
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
                '10': 'RUN',
                '11': 'RUN',
                '12': 'RUN',
                '14': 'PIT',
                '15': 'OUT',
                '16': 'RUN',
                '17': 'RUN',
                '20': 'PIT'
            }
        }
        if not ontrack:
            return 'PIT'
        if raw in states[version]:
            return states[version][raw]
        print "Unknown state: {}".format(raw)
        return "? {}".format(raw)

    def map_car(self, accum):
        def inner(car):
            sector_cols = map(
                lambda s: (parseTime(car.get('S{}TIME'.format(s + 1), '')), ''),
                range(int(self._data.get('NROFINTERMEDIATETIMES', 4)) + 1)
            )

            gap = parseGap(car['GAP'])
            interval = parseGap(car['INT'])
            has_new_lap = CAR_LAP_REGEX.match(str(gap))
            if has_new_lap:
                new_lap = int(has_new_lap.group('lap_num'))
                if 'leader_lap' in accum:
                    gap_laps = accum['leader_lap'] - new_lap
                    gap = '{} lap{}'.format(
                        gap_laps,
                        '' if gap_laps == 1 else 's'
                    )
                else:
                    gap = ''
                    interval = ''
                    accum['leader_lap'] = new_lap

                accum['lap'] = new_lap

            return [
                car['STNR'],
                self.map_car_state(car['LASTINTERMEDIATENUMBER'], car.get('ONTRACK', True)),
                # car['LASTINTERMEDIATENUMBER'],
                car['CLASSNAME'],
                car['CLASSRANK'],
                car['NAME'],
                car['TEAM'],
                car['CAR'],
                accum.get('lap', ''),
                gap,
                interval,
            ] + sector_cols + [
                (parseTime(car['LASTLAPTIME']), ''),
                (parseTime(car['FASTESTLAP']), ''),
                car['PITSTOPCOUNT']
            ]
        return inner

    def postprocess_cars(self, cars):

        colspec = self.getColumnSpec()

        state_idx = colspec.index(Stat.STATE)
        last_lap_idx = colspec.index(Stat.LAST_LAP)
        best_lap_idx = colspec.index(Stat.BEST_LAP)
        first_sector_idx = 10
        last_sector_idx = len(colspec) - 4

        best_sectors = self._data.get('BEST', [])

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
            state = car[state_idx]

            if race_num == fastest[1]:
                car[best_lap_idx] = (best[0], 'sb')
                if last[0] == best[0]:
                    if s5[0] != '' and state == 'RUN':
                        car[last_lap_idx] = (last[0], 'sb-new')
                    else:
                        car[last_lap_idx] = (last[0], 'sb')

            for sector_idx in range(first_sector_idx, last_sector_idx):
                best_sector_idx = sector_idx - first_sector_idx
                if len(best_sectors) > best_sector_idx:
                    best_car, best_time, _, __ = best_sectors[best_sector_idx]
                    if str(best_car) == race_num:
                        parsed_time = parseTime(best_time)
                        if car[sector_idx][0] == parsed_time:
                            car[sector_idx] = [car[sector_idx][0], 'sb']

        return cars
