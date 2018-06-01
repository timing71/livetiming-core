# -*- coding: utf-8 -*-
from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.messages import TimingMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.utils.meteor import MeteorClient, DDPProtoclFactory
from twisted.internet.task import LoopingCall

import argparse
import math
import re
import time


class AlkamelV2Client(MeteorClient):
    def __init__(self, feed_name):
        MeteorClient.__init__(self)

        self._current_session_id = None
        self.session_status_timestamp = None
        self.session_type = 'NONE'

        self._feed_name = feed_name
        self._factory = ReconnectingWebSocketClientFactory('wss://livetiming.alkamelsystems.com/sockjs/261/t48ms2xd/websocket')
        self._factory.protocol = DDPProtoclFactory(self)
        connectWS(self._factory)

        def setSessionStatusTimestamp():
            self.session_status_timestamp = time.time()

        self.on_collection_change('session_info', self.recv_session_info)
        self.on_collection_change('session_status', setSessionStatusTimestamp)

    def onConnect(self):
        self.subscribe('livetimingFeed', [self._feed_name], self.recv_feeds)
        self.subscribe('sessionClasses', [None])

    def recv_feeds(self, _):
        feeds = self.find('feeds')
        self.log.debug("Found feeds: {feeds}", feeds=map(lambda f: f['name'], feeds))

        if len(feeds) == 0:
            raise Exception('No valid feeds found')
        elif len(feeds) > 1:
            self.log.warn("Multiple feeds returned ({feeds}), using {first}", feeds=feeds, first=feeds[0])

        self.subscribe('sessions', [feeds[0]['sessions']])
        self.subscribe('sessionInfo', [feeds[0]['sessions']])

    def recv_session_info(self):
        sessionInfo = self.find('session_info')

        live_sessions = [s for s in sessionInfo if not s.get('info', {}).get('closed', False)]
        if len(live_sessions) == 0:
            self.log.warn("No live sessions detected, instead arbitrarily using {sid}", sid=sessionInfo[0]['session'])
            self.set_session(sessionInfo[0])
        else:
            self.set_session(live_sessions[0])

    def set_session(self, session_info):
        self._current_session_id = session_info['session']
        self.session_type = session_info.get('info', {}).get('type', 'UNKNOWN')
        self.subscribe('entry', [self._current_session_id])
        self.subscribe('trackInfo', [self._current_session_id])
        self.subscribe('standings', [self._current_session_id])
        self.subscribe('sessionStatus', [self._current_session_id])
        self.subscribe('weather', [self._current_session_id])
        self.subscribe('bestResults', [self._current_session_id])
        self.subscribe('raceControl', [self._current_session_id])
        self.subscribe('sessionBestResultsByClass', [self._current_session_id])

        self.emit('session_change', self.find_one('sessions', {'_id': self._current_session_id}), session_info)


class RaceControlMessage(TimingMessage):

    CAR_NUMBER_REGEX = re.compile("car (?P<race_num>[0-9]+)", re.IGNORECASE)

    def __init__(self, client):
        self._client = client
        self._mostRecentTimestamp = 0

    def process(self, _, __):
        rc = self._client.find_one('race_control', {'session': self._client._current_session_id})
        if rc:
            messages = rc.get('raceControlMessages', {}).get('log', {})
            new_messages = [m for m in messages.values() if m.get('date', 0) > self._mostRecentTimestamp]

            msgs = []

            for msg in new_messages:
                hasCarNum = self.CAR_NUMBER_REGEX.search(msg['message'])
                if hasCarNum:
                    msgs.append([msg['date'] / 1000, "Race Control", msg['message'], "raceControl", hasCarNum.group('race_num')])
                else:
                    msgs.append([msg['date'] / 1000, "Race Control", msg['message'], "raceControl"])

                self._mostRecentTimestamp = max(self._mostRecentTimestamp, msg['date'])
            return sorted(msgs, key=lambda m: -m[0])
        return []


def parse_sectors(sectorString, defaultFlag=''):
    sectors = {}
    parts = sectorString.split(';')
    len_parts = len(parts)
    for i in range(len_parts / 6):
        idx = 6 * i
        if len_parts > idx and parts[idx] != '':
            sector = int(parts[idx])
            time = int(parts[idx + 1])
            isPB = parts[idx + 2] == 'true'
            isSB = parts[idx + 3] == 'true'
            isClassBest = parts[idx + 4] == 'true'
            isShowingWhileInPit = parts[idx + 5] == 'true'

            if isSB:
                flag = 'sb'
            elif isPB:
                flag = 'pb'
            elif isShowingWhileInPit:
                flag = 'old'
            else:
                flag = defaultFlag

            sectors[sector] = (time / 1000.0, flag)

    return sectors


CAR_TRACK_STATES = {
    'BOX': 'PIT',
    'OUT_LAP': 'OUT',
    'STOPPED': 'STOP',
    'TRACK': 'RUN'
}

CAR_STATES = {
    'RETIRED': 'RET',
    'NOT_CLASSIFIED': 'DNF',
    'NOT_STARTED': 'N/S',
    'DISQUALIFIED': 'DSQ',
    'EXCLUDED': 'DSQ'
}


# e.lookup("status"), e.lookup("trackStatus"), e.lookup("isRunning"), e.lookup("isCheckered"), e.lookup("isSessionClosed"), false
def map_car_state(status, trackStatus, isRunning, isCheckered):
    if 'CLASSIFIED' == status.upper():
        if isCheckered:
            return 'FIN'
    if status.upper() in CAR_STATES:
        return CAR_STATES[status.upper()]
    if trackStatus.upper() in CAR_TRACK_STATES:
        return CAR_TRACK_STATES[trackStatus.upper()]
    return '???'


FLAG_STATES = {
    'YF': FlagStatus.YELLOW,
    'FCY': FlagStatus.FCY,
    'RF': FlagStatus.RED,
    'SC': FlagStatus.SC,
    'GF': FlagStatus.GREEN
}


def map_flag(flag, isFinished):
    if isFinished:
        return FlagStatus.CHEQUERED.name.lower()
    if flag in FLAG_STATES:
        return FLAG_STATES[flag].name.lower()
    return 'none'


def _parse_loops(loops):
    splits = loops.split(';')
    t = {}

    for r in xrange(0, len(splits) - 1, 2):
        t[int(splits[r])] = int(splits[r + 1])
    return t


def e(t, n, r):
    """ Line 43659-43661 of Al Kamel's JS """
    if t < r:
        if t < 0:
            return n['currentLapStartTime']
        elif t in n['currentLoops']:
            return n['currentLapStartTime'] + n['currentLoops'][t]
        else:
            return n['currentLapStartTime']
    elif t > r:
        if r == -1 and len(n['previousLoops']) == 0:
            return n['currentLapStartTime']
        else:
            return n['currentLapStartTime'] - n['previousLoops'][-1] + n['previousLoops'][t]
    elif t < 0:
        return n['currentLapStartTime']
    return n['currentLapStartTime'] + n['currentLoops'].get(t, 0)


def calculate_gap(first, second):
    if not first:
        return ''

    if not second.get('isRunning', False):
        return ''

    if second.get('currentLapStartTime', 0) == 0 and len(second.get('currentLoops', [])) == 0:
        return ''

    if second.get('currentLapNumber', -1) != -1:
        laps_different = first['currentLapNumber'] - second['currentLapNumber']
    else:
        laps_different = first['laps'] - second['laps']

    if laps_different == 1:
        return "{} lap".format(laps_different)
    elif laps_different > 1:
        return "{} laps".format(laps_different)

    a = len(second['currentLoops']) - 1
    s = second['currentLapStartTime'] + (0 if a < 0 else second['currentLoops'].get(a, 0))
    o = len(first['currentLoops']) - 1
    l = e(a, first, o)

    return abs(s - l) / 1000.0


def calculate_practice_gap(first, second):
    if first and second and first.get('bestLapTime', 0) > 0 and second.get('bestLapTime', 0) > 0:
        return max(0, second['bestLapTime'] - first['bestLapTime']) / 1000.0
    return ''


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", help="Feed ID")
    return parser.parse_args(args)


def maybe_int(mint, default=0):
    try:
        return int(mint)
    except ValueError:
        return default


SECTOR_STATS = [
    Stat.S1,
    Stat.S2,
    Stat.S3,
    Stat.S4,
    Stat.S5,
]


class Service(lt_service):
    attribution = ['Al Kamel Systems', 'http://www.alkamelsystems.com/']
    auto_poll = False

    def __init__(self, args, extra_args, feed=None):
        lt_service.__init__(self, args, extra_args)
        self.feed = feed
        self._prev_session_id = None
        self._client = AlkamelV2Client(self._getFeedName(parse_extra_args(extra_args)))
        self._client.on('session_change', self.on_session_change)

        self._name = 'Al Kamel Timing'
        self._description = ''
        self._has_classes = False
        self._num_sectors = 3

        self._rcMessageGenerator = RaceControlMessage(self._client)

        self._due_publish_state = False

        def set_due_publish():
            self._due_publish_state = True

        self._client.on_collection_change('standings', set_due_publish)
        self._client.on_collection_change('session_status', set_due_publish)
        self._client.on_collection_change('weather', set_due_publish)
        self._client.on_collection_change('best_results', set_due_publish)
        self._client.on_collection_change('race_control', set_due_publish)
        self._client.on_collection_change('sessionBestResultsByClass', set_due_publish)
        self._client.on_collection_change('track_info', self.on_track_info_change)

    def _getFeedName(self, args):
        if self.feed:
            return self.feed
        elif args.feed:
            return args.feed
        else:
            raise RuntimeError("No feed ID specified for Al Kamel! Cannot continue.")

    def start(self):
        def maybePublish():
            if self._due_publish_state:
                self._updateAndPublishRaceState()
                self._due_publish_state = False
        LoopingCall(maybePublish).start(1)

        super(Service, self).start()

    def getName(self):
        return self._name

    def getDefaultDescription(self):
        return self._description

    def getColumnSpec(self):
        base = [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT
        ] + SECTOR_STATS[0:self._num_sectors] + [
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

        if self._has_classes:
            base.insert(2, Stat.CLASS)
            base.insert(3, Stat.POS_IN_CLASS)

        return base

    def getTrackDataSpec(self):
        return [
            'Air Temp',
            'Track Temp',
            'Humidity',
            'Wind Speed'
        ]

    def getExtraMessageGenerators(self):
        return [
            self._rcMessageGenerator
        ]

    def on_session_change(self, new_session, session_info):
        if self._prev_session_id and new_session['id'] != self._prev_session_id:
            self.analyser.reset()
        info = session_info.get('info', {})
        self._name = info.get('champName', 'Al Kamel Timing')
        self._description = "{} - {}".format(
            info.get('eventName', ''),
            new_session.get('name', '')
        )
        self._prev_session_id = new_session['id']
        self.publishManifest()

    def on_track_info_change(self):
        track_info = self._client.find_one('track_info', {'session': self._client._current_session_id})
        if track_info:
            sector_count = len(track_info.get('track', {}).get('sectors', {}))
            if sector_count != self._num_sectors:
                self.log.info('Reconfiguring with {num} track sectors', num=sector_count)
                if sector_count > 5:
                    self.log.warn('Too many sectors! Limiting to 5.')
                    self._num_sectors = 5
                else:
                    self._num_sectors = sector_count
                self.publishManifest()

    def _set_has_classes(self, has_classes):
        if has_classes != self._has_classes:
            self._has_classes = has_classes
            self.publishManifest()

    def getRaceState(self):
        # print self._client.collection_data.collections()
        return {
            'session': self._map_session(),
            'cars': self._map_standings()
        }

    def _map_standings(self):
        gap_func = calculate_gap if self._client.session_type == 'RACE' else calculate_practice_gap
        standings_data = self._client.find_one('standings', {'session': self._client._current_session_id})
        entries_data = self._client.find_one('session_entry', {'session': self._client._current_session_id})

        best_lap_data = self._client.find_one('best_results', {'session': self._client._current_session_id})
        overall_best_lap = best_lap_data.get('bestResults', {}).get('bestLap', {}) if best_lap_data else {}

        best_class_lap_data = self._client.find_one('sessionBestResultsByClass', {'session': self._client._current_session_id})
        class_best_laps = best_class_lap_data.get('bestResultsByClass', {}).get('bestLapsByClass', {}) if best_class_lap_data else {}

        if standings_data and entries_data:

            has_classes = standings_data.get('standings', {}).get('hasClasses', False)
            self._set_has_classes(has_classes)

            standings = standings_data.get('standings', {}).get('standings', {})
            entries = entries_data.get('entry', {})

            if standings and entries:
                cars = []
                prev_car = None
                lead_car = None
                class_count = {}

                for position in sorted(map(int, standings.keys())):
                    data = standings[str(position)]
                    if 'data' in data:
                        standing_data = data['data'].split(";")
                        race_num = standing_data[1]
                        entry = entries.get(race_num, {})
                        clazz = entry.get('class', '')

                        current_sectors = parse_sectors(data.get('currentSectors', ''))
                        previous_sectors = parse_sectors(data.get('lastSectors', ''), 'old')

                        data_with_loops = {
                            'currentLoops': _parse_loops(data.get('currentLoopSectors')),
                            'previousLoops': _parse_loops(data.get('previousLoopSectors')),
                            'currentLapStartTime': maybe_int(standing_data[7], 0),
                            'currentLapNumber': maybe_int(standing_data[9], 0),
                            'laps': maybe_int(standing_data[4], 0)
                        }
                        data_with_loops.update(data)

                        status = standing_data[2]
                        trackStatus = standing_data[8]

                        state = map_car_state(status, trackStatus, data.get('isRunning', False), data.get('isCheckered', False))

                        last_lap = data.get('lastLapTime', 0) / 1000.0
                        best_lap = data.get('bestLapTime', 0) / 1000.0

                        last_lap_flag = 'pb' if data.get('isLastLapBestPersonal', False) else ''

                        has_overall_best = overall_best_lap.get('participantNumber') == race_num
                        has_class_best = clazz and class_best_laps.get(clazz, {}).get('participantNumber') == race_num

                        if has_overall_best or has_class_best:
                            best_lap_flag = 'sb'
                            if last_lap == best_lap and 3 in current_sectors:
                                last_lap_flag = 'sb-new'
                        else:
                            best_lap_flag = ''

                        sector_cols = []
                        for i in range(self._num_sectors):
                            sector_cols.append(
                                current_sectors.get(i + 1, previous_sectors.get(i + 1, ''))
                            )

                        car = [
                            race_num,
                            state,
                            u"{}, {}".format(entry.get('lastname', ''), entry.get('firstname', '').title()),
                            entry.get('team', ''),
                            entry.get('vehicle', ''),
                            standing_data[4],
                            gap_func(lead_car, data_with_loops),
                            gap_func(prev_car, data_with_loops)
                        ] + sector_cols + [
                            (last_lap if last_lap > 0 else '', last_lap_flag),
                            (best_lap if best_lap > 0 else '', best_lap_flag),
                            standing_data[5]
                        ]

                        if self._has_classes:
                            class_count[clazz] = class_count.get(clazz, 0) + 1
                            car.insert(2, clazz)
                            car.insert(3, class_count[clazz])

                        cars.append(car)

                    prev_car = data_with_loops
                    if not lead_car:
                        lead_car = data_with_loops

                return cars

        return []

    def _map_session(self):
        result = {
            'flagState': 'none',
            'timeElapsed': 0,
            'trackData': self._map_track_data()
        }

        status_data = self._client.find_one('session_status', {'session': self._client._current_session_id})
        if status_data:
            status = status_data.get('status')
            if status:
                result['flagState'] = map_flag(status.get('currentFlag', 'none'), status.get('isFinished', False))

                startTime = status.get('startTime', 0)
                stopTime = status.get('stopTime', 0)
                finalTime = status.get('finalTime', 0)
                stoppedSeconds = status.get('stoppedSeconds', 0)
                sessionRunning = status.get('isSessionRunning', False)
                now = time.time()

                if status.get('isForcedByTime', False) or status.get('finalType') == "BY_TIME" or status.get('finalType') == "BY_TIME_PLUS_LAPS":
                    if sessionRunning:
                        result['timeRemain'] = (startTime + finalTime) - now - stoppedSeconds
                    else:
                        result['timeRemain'] = (startTime + finalTime) - stopTime - now - stoppedSeconds
                else:
                    result['lapsRemain'] = max(0, status.get('finalLaps', 0) - status.get('elapsedLaps', 0))

                if startTime > 0:
                    startTimestamp = datetime.utcfromtimestamp(startTime)
                    if stopTime > 0 and not sessionRunning:
                        result['timeElapsed'] = (stopTime - startTime)
                    else:
                        result['timeElapsed'] = (now - startTime) - status.get('stoppedSeconds', 0)

        return result

    def _map_track_data(self):
        weather_data = self._client.find_one('weather', {'session': self._client._current_session_id})
        if weather_data:
            weather = weather_data.get('weather')
            if weather:
                return [
                    u"{:.3g}°C".format(weather.get('ambientTemperature', '')),
                    u"{:.3g}°C".format(weather.get('trackTemperature', '')),
                    "{}%".format(weather.get('humidity', '')),
                    "{:.2g} km/h".format(weather.get('windSpeed', '')),
                ]
        return []
