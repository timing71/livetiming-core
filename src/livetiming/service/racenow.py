from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.messages import RaceControlMessage
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import re
import simplejson
import time
import urllib2

# We'll probably want to use this at some point
# SERVER_SPEC_URL = 'http://52.36.59.170/data/server/server.json'


def create_ws_protocol(log, handler):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            log.info('Connected to upstream timing source')
            self.factory.resetDelay()

        def onMessage(self, payload, isBinary):
            log.debug('Received message: \'{msg}\'', msg=payload)
            if len(payload) > 0:
                handler(simplejson.loads(payload))

    return ClientProtocol


class RaceNowState:
    def __init__(self, log, onSessionChange, onData):
        self.log = log
        self.onSessionChange = onSessionChange
        self.onData = onData
        self._reset()

    def _reset(self):
        self.has_data = False
        self.session = {}
        self.cars = {}
        self.flag = {}
        self.weather = {}

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
        self.session.update(payload)
        self.onSessionChange()

    def handle_0(self, payload):
        for line in payload.get('rows', []):
            self.cars[line['CARNO']] = line

    def handle_F(self, payload):
        self.flag.update(payload)

    def handle_W(self, payload):
        self.weather.update(payload)

    def handle_L(self, payload):
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

    def _update_car_with(payload):
        if 'CARNO' in payload:
            car_num = payload['CARNO']
            if car_num in self.cars:
                self.cars[car_num].update(payload)


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--tk', help='Track (Suzuka, Motegi or one of their variants)', required=True, metavar='TRACK')
    parser.add_argument('--name', help='Name for the service', required=True)
    return parser.parse_args(extra_args)


def car_sort_key(sessionType):
    def inner(car):
        if car['RUN_FLAG'] == "1":
            if sessionType == 'R':
                return (int(car.get('LAPS', 0)) * 10000000) - float(car.get('TOTAL_TIME', 0))
            else:
                return float(car.get('BEST_TIME', 0)) * -1
        else:
            return int(car.get('START_POS', 0))
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


def maybe_time(time):
    try:
        ftime = float(time)
        if ftime > 0:
            return ftime
        return ''
    except ValueError:
        return time


def maybe_int(raw):
    try:
        return int(raw)
    except ValueError:
        return raw


def map_car(car):
    return [
        car['REGNO'],
        map_car_state(car.get('STATUS', '')),
        car.get('RACE_CLASS', ''),
        car.get('DRIVER_E', ''),
        car.get('TEAM_E', ''),
        maybe_int(car.get('LAPS', 0)),
        car.get('TIRE', ''),
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


class Service(lt_service):
    auto_poll = False

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._state = RaceNowState(
            self.log,
            self.onSessionChange,
            self._updateAndPublishRaceState
        )

        url = 'ws://52.24.223.254:9001/get'

        factory = ReconnectingWebSocketClientFactory(url)
        factory.protocol = create_ws_protocol(self.log, self._state.handle)
        connectWS(factory)

    def _getServiceClass(self):
        return self._extra.tk

    def onSessionChange(self):
        self.state['messages'] = []
        self.analyser.reset()
        self.publishManifest()

    def getRaceState(self):
        if not self._state.has_data:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
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
        return self._extra.name

    def getDefaultDescription(self):
        return self._state.session.get('DESCR_E', '')

    def getTrackDataSpec(self):
        return ['Weather']

    def _mapCars(self):

        session_type = self._state.session.get('RACE_TYPE', 'B')

        sort_func = car_sort_key(session_type)
        cars = map(map_car, sorted(self._state.cars.values(), key=sort_func, reverse=True))

        if len(cars) > 0:  # Now we need to calculate gap/int from the original dataset
            leader = self._state.cars[cars[0][0]]
            leader_laps = int(leader.get('LAPS', 0))

            for idx, car in enumerate(cars[1:]):
                this_car = self._state.cars[car[0]]
                this_laps = int(this_car.get('LAPS', 0))
                prev_car = self._state.cars[cars[idx][0]]
                prev_laps = int(prev_car.get('LAPS', 0))

                gap = ''
                interval = ''

                if session_type == 'R':
                    if this_laps < leader_laps:
                        gap_laps = leader_laps - this_laps
                        gap = '{} lap{}'.format(gap_laps, 's' if gap_laps > 1 else '')
                    else:
                        gap = float(this_car.get('TOTAL_TIME', 0)) - float(leader.get('TOTAL_TIME', 0))

                    if this_laps < prev_laps:
                        int_laps = prev_laps - this_laps
                        interval = '{} lap{}'.format(int_laps, 's' if int_laps > 1 else '')
                    else:
                        interval = float(this_car.get('TOTAL_TIME', 0)) - float(prev_car.get('TOTAL_TIME', 0))

                elif this_car.get('BEST_TIME', 0) != '9999999999':
                    gap = float(this_car.get('BEST_TIME', 0)) - float(leader.get('BEST_TIME', 0))
                    interval = float(this_car.get('BEST_TIME', 0)) - float(prev_car.get('BEST_TIME', 0))

                car[7] = gap
                car[8] = interval

        return cars

    def _mapSession(self):
        return {
            "flagState": map_session_flag(self._state.flag.get('flag', '')).name.lower(),
            "timeElapsed": 0,
            "trackData": [ self._state.weather.get('condition', '') ]
        }
