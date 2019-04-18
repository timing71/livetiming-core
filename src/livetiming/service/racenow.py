from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.messages import RaceControlMessage
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.internet.task import LoopingCall

import argparse
import re
import simplejson
import time
import urllib.request, urllib.error, urllib.parse

SERVER_SPEC_URL = 'http://52.36.59.170/data/server/server.json'


def create_ws_protocol(log, handler):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            log.info('Connected to upstream timing source')
            self.factory.resetDelay()

        def onMessage(self, payload, isBinary):
            log.debug('Received message: \'{msg}\'', msg=payload)
            if len(payload) > 0:
                handler(simplejson.loads(payload.decode()))

    return ClientProtocol


class RaceNowState:
    def __init__(self, log, onSessionChange, onData):
        self.log = log
        self.onSessionChange = onSessionChange
        self.onData = onData
        self.messages = []
        self._reset()

    def _reset(self):
        self.has_data = False
        self.session = {}
        self.cars = {}
        self.flag = {}
        self.weather = {}
        del self.messages[:]

    def handle(self, payload):
        if 'type' in payload:
            type_handler = 'handle_{}'.format(payload['type'])
            if hasattr(self, type_handler):
                attr = getattr(self, type_handler)
                if callable(attr):
                    attr(payload)
                    self.onData()
                    return
            self.log.warn('Unhandled message type {type}', type=payload['type'])

    def handle_S(self, payload):
        old_session = self.session.get('DESCR_E')
        is_new_session = payload.get('DESCR_E') != old_session
        if is_new_session:
            self._reset()
        self.session.update(payload)
        if is_new_session:
            self.onSessionChange()

    def handle_0(self, payload):
        for line in payload.get('rows', []):
            self.cars[line['CARNO']] = line

    def handle_F(self, payload):
        self.flag.update(payload)

    def handle_W(self, payload):
        self.weather.update(payload)

    def handle_1(self, payload):
        self._update_car_with(payload)

    def handle_2(self, payload):
        self._update_car_with(payload)

    def handle_3(self, payload):
        self._update_car_with(payload)

    def handle_L(self, payload):
        self._update_car_with(payload)

    def handle_K(self, payload):
        self._update_car_with(payload)

    def handle_U(self, payload):
        self._update_car_with(payload)

    def handle_D(self, payload):
        self._update_car_with(payload)

    def handle_I(self, payload):
        self._update_car_with({
            'CARNO': payload.get('CARNO'),
            'PIT': payload.get('PIT'),
            'STATUS': 'P'
        })

    def handle_O(self, payload):
        self._update_car_with({
            'CARNO': payload.get('CARNO'),
            'STATUS': ''
        })

    def handle_R(self, payload):
        print("Reset request received")

    def handle_T(self, payload):
        self._handle_rc_message(payload['msg'])

    def handle_T2(self, payload):
        self._handle_rc_message(payload['msg'])

    def _update_car_with(self, payload):
        if 'CARNO' in payload:
            car_num = payload['CARNO']
            if car_num in self.cars:
                self.cars[car_num].update(payload)

    def _handle_rc_message(self, msg):
        stripped = msg.strip()
        if stripped != '':
            self.messages.append(stripped)


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--tk', help='Track (Suzuka, Motegi or one of their variants)', metavar='TRACK')
    parser.add_argument('-w', '--ws', help='WebSocket URL to connect to (instead of track name)')
    parser.add_argument('--name', help='Name for the service')
    return parser.parse_args(extra_args)


def car_sort_key(sessionType):
    def inner(car):
        if car['RUN_FLAG'] == "1":
            if sessionType == 'R':
                return (int(car.get('LAPS', 0)) * 10000000) - float(car.get('TOTAL_TIME', 0))
            else:
                return float(car.get('BEST_TIME', 0)) * -1
        else:
            return -99999 - int(car.get('START_POS', 0))
    return inner


def map_car_state(state):
    if state == 'P':
        return 'PIT'
    return 'RUN'


_TIME_FLAGS = {
    '0': '',
    '1': 'pb',
    '2': 'sb'
}


def map_time_flag(flag):
    return _TIME_FLAGS.get(flag, '')


def maybe_time(raw):
    try:
        ftime = float(raw)
        if ftime > 0:
            return ftime
        return ''
    except ValueError:
        return raw


def maybe_float(raw):
    if raw == '' or raw is None:
        return 0
    try:
        return float(raw)
    except ValueError as e:
        return 0


def maybe_int(raw):
    try:
        return int(raw)
    except ValueError:
        return raw


TYRE_MAP = {
    'M': 'tyre-hard',
    'S': 'tyre-soft'
}


def map_tyre(t):
    return [t, TYRE_MAP.get(t, '')]


def map_car(car):
    return [
        car['CARNO'],
        map_car_state(car.get('STATUS', '')),
        car.get('RACE_CLASS', ''),
        car.get('DRIVER_E', ''),
        car.get('TEAM_E', ''),
        maybe_int(car.get('LAPS', 0)),
        map_tyre(car.get('TIRE', '')),
        '',
        '',
        [maybe_time(car.get('SEC1_TIME', 0)), map_time_flag(car.get('SEC1_FLAG'))],
        [maybe_time(car.get('SEC1_BEST_TIME', 0)), 'old'],
        [maybe_time(car.get('SEC2_TIME', 0)), map_time_flag(car.get('SEC2_FLAG'))],
        [maybe_time(car.get('SEC2_BEST_TIME', 0)), 'old'],
        [maybe_time(car.get('SEC3_TIME', 0)), map_time_flag(car.get('SEC3_FLAG'))],
        [maybe_time(car.get('SEC3_BEST_TIME', 0)), 'old'],
        [maybe_time(car.get('SEC4_TIME', 0)), map_time_flag(car.get('SEC4_FLAG'))],
        [maybe_time(car.get('SEC4_BEST_TIME', 0)), 'old'],
        [maybe_time(car.get('LAST_TIME', 0)), map_time_flag(car.get('LAST_FLAG'))],
        [maybe_time(car.get('BEST_TIME', 0)), ''],
        maybe_int(car.get('PIT', 0))
    ]


_SESSION_FLAGS = {
    'R': FlagStatus.RED,
    'G': FlagStatus.GREEN,
    'Y': FlagStatus.SC,
    'F': FlagStatus.CHEQUERED
}


def map_session_flag(raw):
    return _SESSION_FLAGS.get(
        raw,
        FlagStatus.NONE
    )


def get_websocket_url(extra_args):
    if extra_args.tk:
        servers = simplejson.load(urllib.request.urlopen(SERVER_SPEC_URL))

        track_ip_key = '{}_server'.format(track)
        track_port_key = '{}_port1'.format(track)

        if track_ip_key in servers and track_port_key in servers:
            return 'ws://{}:{}/get'.format(
                servers[track_ip_key],
                servers[track_port_key]
            )

        raise Exception('Cannot find {} in server config: {}'.format(track, list(servers.keys())))
    elif extra_args.ws:
        return extra_args.ws
    else:
        raise Exception('Either track name or websocket URL must be specified')


class Service(lt_service):
    auto_poll = False
    attribution = ['RaceLive', 'http://racenow.racelive.jp/']

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]

        self._pending_update = False

        def setPendingUpdate():
            self._pending_update = True

        def maybeSendUpdate():
            if self._pending_update:
                self._pending_update = False
                self._updateAndPublishRaceState()

        self._state = RaceNowState(
            self.log,
            self.onSessionChange,
            setPendingUpdate
        )

        url = get_websocket_url(self._extra)

        factory = ReconnectingWebSocketClientFactory(url)
        factory.protocol = create_ws_protocol(self.log, self._state.handle)
        connectWS(factory)

        LoopingCall(maybeSendUpdate).start(1)

    def _getServiceClass(self):
        return self._extra.tk

    def onSessionChange(self):
        self.log.info("Session change triggered")
        self.state['messages'] = []
        self.analyser.reset()
        self.publishManifest()

    def getRaceState(self):
        return {
            'cars': self._mapCars(),
            'session': self._mapSession()
        }

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.LAPS,
            Stat.TYRE,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.BS1,
            Stat.S2,
            Stat.BS2,
            Stat.S3,
            Stat.BS3,
            Stat.S4,
            Stat.BS4,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getName(self):
        if self._extra.name:
            return self._extra.name
        raise Exception('No service name specified (-n)')

    def getDefaultDescription(self):
        return self._state.session.get('DESCR_E', '')

    def getTrackDataSpec(self):
        return ['Weather']

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self._state.messages)
        ]

    def _mapCars(self):

        session_type = self._state.session.get('RACE_TYPE', 'B')

        sort_func = car_sort_key(session_type)
        cars = list(map(map_car, sorted(list(self._state.cars.values()), key=sort_func, reverse=True)))

        if len(cars) > 0:  # Now we need to calculate gap/int from the original dataset, and highlight sb's
            leader = self._state.cars[cars[0][0]]
            leader_laps = maybe_int(leader.get('LAPS', 0))

            sb_lap_car = self._state.session.get('LAP_BEST_NO')
            sb_lap_time = maybe_float(self._state.session.get('LAP_BEST_TIME'))

            sb_s1_car = self._state.session.get('S1_BEST_NO')
            sb_s1_time = maybe_float(self._state.session.get('S1_BEST_TIME'))

            sb_s2_car = self._state.session.get('S2_BEST_NO')
            sb_s2_time = maybe_float(self._state.session.get('S2_BEST_TIME'))

            sb_s3_car = self._state.session.get('S3_BEST_NO')
            sb_s3_time = maybe_float(self._state.session.get('S3_BEST_TIME'))

            sb_s4_car = self._state.session.get('S4_BEST_NO')
            sb_s4_time = maybe_float(self._state.session.get('S4_BEST_TIME'))

            for idx, car in enumerate(cars):
                if idx > 0:
                    this_car = self._state.cars[car[0]]
                    this_laps = maybe_int(this_car.get('LAPS', 0))
                    prev_car = self._state.cars[cars[idx - 1][0]]
                    prev_laps = maybe_int(prev_car.get('LAPS', 0))

                    gap = ''
                    interval = ''

                    if session_type == 'R':
                        if this_laps < leader_laps:
                            gap_laps = leader_laps - this_laps
                            gap = '{} lap{}'.format(gap_laps, 's' if gap_laps > 1 else '')
                        else:
                            gap = maybe_float(this_car.get('TOTAL_TIME', 0)) - maybe_float(leader.get('TOTAL_TIME', 0))

                        if this_laps < prev_laps:
                            int_laps = prev_laps - this_laps
                            interval = '{} lap{}'.format(int_laps, 's' if int_laps > 1 else '')
                        else:
                            interval = maybe_float(this_car.get('TOTAL_TIME', 0)) - maybe_float(prev_car.get('TOTAL_TIME', 0))

                    elif this_car.get('BEST_TIME', 0) != '9999999999':
                        gap = maybe_float(this_car.get('BEST_TIME', 0)) - maybe_float(leader.get('BEST_TIME', 0))
                        interval = maybe_float(this_car.get('BEST_TIME', 0)) - maybe_float(prev_car.get('BEST_TIME', 0))

                    car[7] = gap if isinstance(gap, str) or gap >= 0 else ''
                    car[8] = interval if isinstance(interval, str) or interval >= 0 else ''

                if car[0] == sb_lap_car and car[18][0] == sb_lap_time:
                    car[18] = [car[18][0], 'sb-new' if car[17][0] == car[18][0] and car[15][0] != '' else 'sb']

                if car[0] == sb_s1_car and car[10][0] == sb_s1_time:
                    car[10] = [car[10][0], 'sb']

                if car[0] == sb_s2_car and car[11][0] == sb_s2_time:
                    car[12] = [car[12][0], 'sb']

                if car[0] == sb_s3_car and car[13][0] == sb_s3_time:
                    car[14] = [car[14][0], 'sb']

                if car[0] == sb_s4_car and car[15][0] == sb_s4_time:
                    car[16] = [car[16][0], 'sb']

        return cars

    def _mapSession(self):
        session = {
            "flagState": map_session_flag(self._state.flag.get('flag', '')).name.lower(),
            "trackData": [self._state.weather.get('condition', '-')]
        }

        to_go = self._state.flag.get('togo', '')

        if re.match("[0-9]{2}:[0-9]{2}:[0-9]{2}", to_go):
            times = list(map(int, to_go.split(':')))
            session['timeRemain'] = (times[0] * 3600) + (times[1] * 60) + times[2]

        return session
