from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
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


def map_flag(raw):
    mapp = {
        'Yellow': FlagStatus.SC,
        'Green': FlagStatus.GREEN,
        'Red': FlagStatus.RED,
        'Checkered': FlagStatus.CHEQUERED,
        'WaitStart': FlagStatus.NONE
    }
    if raw in mapp:
        return mapp[raw]
    print "Unknown flag {}".format(raw)
    return FlagStatus.NONE


class NatsoftState(object):

    HANDLERS = {
        'CategoryList': 'children',
        'CompetitorList': 'children',
        'Grid': 'ignore',
        'Leaderboard': 'children',
        'Passing': 'ignore',
        'PointsSeries': 'ignore',
        'PointsTeam': 'ignore',
        'Sectors': 'ignore',
        'Track': 'ignore'
    }

    def __init__(self, logger, onSessionChange=None):
        self.log = logger
        self._reset()
        self.onSessionChange = onSessionChange

    def _reset(self):
        self.has_data = False
        self._categories = {}
        self._positions = {}
        self._session = {
            'flag': FlagStatus.NONE
        }
        self._competitors = {}
        self._name = ''
        self._description = ''

    def handle(self, xml):
        if xml.tag in self.HANDLERS:
            handler_name = "handle_{}".format(self.HANDLERS[xml.tag])
            self.log.debug("Invoking handler {handler_name}", handler_name=handler_name)
            getattr(self, handler_name)(xml)
        else:
            handler_name = "handle_{}".format(xml.tag.lower())
            if hasattr(self, handler_name):
                self.log.debug("Invoking handler {handler_name}", handler_name=handler_name)
                getattr(self, handler_name)(xml)
            else:
                self.log.warn("Unhandled XML tag: {tag}", tag=xml.tag)
                ET.dump(xml)

    def handle_new(self, xml):
        self.log.info("Starting new event session")
        self._reset()
        self.has_data = True

        self.handle_children(xml)
        if self.onSessionChange:
            self.onSessionChange()

    def handle_children(self, xml):
        for child in xml:
            self.handle(child)

    def handle_ignore(self, xml):
        pass

    def handle_meeting(self, xml):
        self._name = xml.get('Description')

    def handle_event(self, xml):
        self._description = xml.get('Description1')

    def handle_category(self, xml):
        self._categories[xml.get('ID')] = xml.get('Code')

    def handle_competitor(self, competitor):
        self._competitors[competitor.get('ID')] = {
            'category': self._categories[competitor.get('Category')],
            'name': competitor.get('TeamName').replace('_', ' '),
            'number': competitor.get('Number'),
            'vehicle': competitor.get('Vehicle'),
            'drivers': {d.get('ID'): d.get('Name').replace('_', ' ') for d in competitor.findall('Driver')}
        }

    def handle_position(self, position):
        competitor = self._competitors[position.get('Comp')]
        pos = self._positions.setdefault(int(position.get('Pos')), {})

        pos['competitor'] = competitor
        pos['driver'] = competitor['drivers'][position.get('Driv')]

        self.process_position_detail(pos, position.find('Detail'))

    def process_position_detail(self, pos, detail):
        pos['tyre'] = detail.get('TyreType', pos.get('tyre', ''))
        pos['laps'] = detail.get('LastLap', pos.get('laps', ''))
        pos['s1'] = detail.get('LastSec1Time', pos.get('s1', ''))
        pos['s2'] = detail.get('LastSec2Time', pos.get('s2', ''))
        pos['s3'] = detail.get('LastSec3Time', pos.get('s3', ''))
        pos['bs1'] = detail.get('FastSec1Time', pos.get('bs1', ''))
        pos['bs2'] = detail.get('FastSec2Time', pos.get('bs2', ''))
        pos['bs3'] = detail.get('FastSec3Time', pos.get('bs3', ''))
        pos['last'] = detail.get('LastTime', pos.get('last', ''))
        pos['best'] = detail.get('FastTime', pos.get('best', ''))

        pos['gap_laps'] = detail.get('GapLeadLap', pos.get('gap_laps', 0))
        pos['int_laps'] = detail.get('GapNextLap', pos.get('int_laps', 0))

        pos['gap_time'] = detail.get('GapLeadTime', pos.get('gap_time', 0))
        pos['int_time'] = detail.get('GapNextTime', pos.get('int_time', 0))

        pos['pits'] = int(detail.get('PitStops', pos.get('pits', 0)))

        pos['state'] = detail.get('PitLaneFlag', pos.get('state', ''))

    def handle_counters(self, counters):
        raw_flag = counters.get('Status', None)
        if raw_flag:
            self._session['flag'] = map_flag(raw_flag)
        self._session['elapsed'] = (int(counters.get('Elapsed')), time.time())
        self._session['counter'] = (int(counters.get('Count')), counters.get('Type'))


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--url', help='WebSocket URL to connect to')
    parser.add_argument('--host', help='Host to connect to for a TCP connection')
    parser.add_argument('-p', '--port', help='Port to connect to for a TCP connection', type=int)
    parser.add_argument('-n', '--name', help='Service name', default='Natsoft timing feed')

    return parser.parse_args(extra_args)


def map_car_state(state):
    mapp = {
        'P': 'PIT',
        '': 'RUN'
    }
    if state in mapp:
        return mapp[state]
    return state


def map_tyre(tyreChar):
    tyreMap = {
        "H": ("H", "tyre-hard"),
        "M": ("M", "tyre-med"),
        "S": ("S", "tyre-soft"),
        "V": ("SS", "tyre-ssoft"),
        "E": ("US", "tyre-usoft"),
        "I": ("I", "tyre-inter"),
        "W": ("W", "tyre-wet"),
        "U": ("U", "tyre-development")
    }
    return tyreMap.get(tyreChar, tyreChar)


def format_gap(laps, time):
    try:
        lap_int = int(laps)
        if lap_int == 1:
            return '1 lap'
        elif lap_int > 1:
            return '{} laps'.format(laps)
        if float(time) > 0:
            return time
        return ''
    except ValueError:
        return time


def map_car(car):
    competitor = car['competitor']

    s1 = float(car.get('s1', 0))
    s2 = float(car.get('s2', 0))
    s3 = float(car.get('s3', 0))
    bs1 = float(car.get('bs1', 0))
    bs2 = float(car.get('bs2', 0))
    bs3 = float(car.get('bs3', 0))

    s1_flag = 'pb' if s1 == bs1 else ''
    s2_flag = 'pb' if s2 == bs2 else ''
    s3_flag = 'pb' if s3 == bs3 else ''

    try:
        last = float(car.get('last', 0))
    except ValueError:
        last = 0

    try:
        best = float(car.get('best', 0))
    except ValueError:
        best = 0

    last_flag = 'pb' if last == best else ''
    pits = car.get('pits', 0)

    return [
        competitor['number'],
        map_car_state(car.get('state', '')),
        competitor['category'],
        car['driver'],
        competitor['name'],
        competitor['vehicle'],
        car.get('laps', ''),
        map_tyre(car.get('tyre', '')),
        format_gap(car.get('gap_laps', 0), car.get('gap_time', 0)),
        format_gap(car.get('int_laps', 0), car.get('int_time', 0)),
        (s1, s1_flag) if s1 > 0 else '',
        (car.get('bs1', ''), 'old'),
        (s2, s2_flag) if s2 > 0 else '',
        (car.get('bs2', ''), 'old'),
        (s3, s3_flag) if s3 > 0 else '',
        (car.get('bs3', ''), 'old'),
        (last, last_flag) if last > 0 else '',
        (best, '') if best > 0 else '',
        pits if pits > 0 else ''
    ]


class Service(lt_service):
    attribution = ['Natsoft', 'http://racing.natsoft.com.au']

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._state = NatsoftState(self.log, self.onSessionChange)

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

    def onSessionChange(self):
        self.analyser.reset()
        self.publishManifest()

    def getName(self):
        if self._state.has_data:
            return self._state._name
        return self._extra.name

    def getDefaultDescription(self):
        if self._state.has_data:
            return self._state._description
        return ''

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.CAR,
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
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getPollInterval(self):
        return 1

    def getRaceState(self):
        if not self._state.has_data:
            print "State has no data"
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0
                }
            }

        elapsed = self._state._session['elapsed']

        session = {
            'flagState': self._state._session['flag'].name.lower(),
            'timeElapsed': int(elapsed[0] + (time.time() - elapsed[1]))
        }

        if 'counter' in self._state._session:
            value, count_type = self._state._session['counter']
            if count_type == 'Laps':
                session['lapsRemain'] = value

        return {
            'cars': map(map_car, [value for (key, value) in sorted(self._state._positions.items())]),
            'session': session
        }
