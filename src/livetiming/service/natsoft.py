from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.messages import RaceControlMessage
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.racing import FlagStatus, Stat
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, ReconnectingClientFactory

import argparse
import re
import time
import urllib.request, urllib.error, urllib.parse
import xml.etree.ElementTree as ET


# Natsoft demo stream: natsoft.com.au:8889
# (Different, unsupported format at :8888)

def create_ws_protocol(log, handler):
    class ClientProtocol(WebSocketClientProtocol):

        def onConnect(self, response):
            log.info('Connected to upstream timing source')
            self.factory.resetDelay()

        def onMessage(self, payload, isBinary):
            log.debug('Received message: {msg}', msg=payload)

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
        'Ended': FlagStatus.CHEQUERED,
        'WaitStart': FlagStatus.NONE
    }
    if raw in mapp:
        return mapp[raw]
    print("Unknown flag {}".format(raw))
    return FlagStatus.NONE


class NatsoftState(object):

    HANDLERS = {
        'CategoryList': 'children',
        'CompetitorList': 'children',
        'Grid': 'ignore',
        'H': 'ignore',
        'Heartbeat': 'ignore',
        'Leaderboard': 'children',
        'L': 'children',
        'OL': 'ignore',  # Lap record
        'OS': 'children',
        'Passing': 'ignore',
        'PointsSeries': 'ignore',
        'PointsTeam': 'ignore',
        'RL': 'children',
        'Sectors': 'ignore',
        'T': 'ignore',  # Timing point IDs and names
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
        self.messages = []

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
        # Actually new, or just a periodic reset?
        actual_reset = False
        e_tag = xml.find('E')
        event_tag = xml.find('Event')

        if e_tag is not None:
            evt_description = e_tag.get('D')
            actual_reset = evt_description != self._description
        elif event_tag is not None:
            evt_description = event_tag.get('Description1')
            actual_reset = evt_description != self._description

        if actual_reset:
            self.log.info("Starting new event session")
            self._reset()
        self.has_data = True

        self.handle_children(xml)
        if self.onSessionChange and actual_reset:
            self.onSessionChange()

    def handle_children(self, xml):
        for child in xml:
            self.handle(child)

    def handle_ignore(self, xml):
        pass

    def handle_meeting(self, xml):
        self._name = xml.get('Description')

    def handle_m(self, xml):
        self._name = xml.get('D')

    def handle_event(self, xml):
        self._description = xml.get('Description1')

    def handle_e(self, xml):
        self._description = xml.get('D')

    def handle_category(self, xml):
        self._categories[xml.get('ID')] = xml.get('Code')

    def handle_o(self, o):
        self._categories[o.get('ID')] = o.get('C')

    def handle_message(self, message):
        r = message.get('Control', None)
        if r:
            self.messages.append(r)
        c = message.get('Corporate', None)
        if c:
            self.messages.append(c)

    def handle_g(self, g):
        # <G C="" R="" T="1517565375.4542" />
        r = g.get('R', None)
        if r:
            self.messages.append(r)
        c = g.get('C', None)
        if c:
            self.messages.append(c)

    def handle_fastest(self, f):
        sb = self._session.setdefault('sb', [0, 0, 0, 0])
        sb[0] = float(f.get('LapTime', sb[0]))
        sb[1] = float(f.get('Sec1Time', sb[1]))
        sb[2] = float(f.get('Sec2Time', sb[2]))
        sb[3] = float(f.get('Sec3Time', sb[3]))
        # ET.dump(f)

    def handle_a(self, a):
        # <A C="1" I="128.5909" I1="52.0654" I2="86.7373" S1="52.0654" S2="33.7138" S3="41.4021" T="1517561801.8834" Y="f" />
        sb = self._session.setdefault('sb', [0, 0, 0, 0])
        sb[0] = float(a.get('I', sb[0]))
        sb[1] = float(a.get('S1', sb[1]))
        sb[2] = float(a.get('S2', sb[2]))
        sb[3] = float(a.get('S3', sb[3]))
        # ET.dump(a)

    def handle_r(self, competitor):
        # ET.dump(competitor)
        cat = competitor.get('S')
        self._competitors[competitor.get('ID')] = {
            'category': self._categories.get(cat, cat),
            'name': '',
            'number': competitor.get('N'),
            'vehicle': competitor.get('V'),
            'drivers': {d.get('ID'): d.get('N').replace('_', ' ') for d in competitor.findall('V')}
        }

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

        try:
            pos = self._positions.setdefault(int(position.get('Pos')), {})
        except ValueError:
            pos = self._positions.setdefault(int(position.get('Line')), {})

        pos['competitor'] = competitor
        pos['driver'] = competitor['drivers'][position.get('Driv')]

        detail = position.find('Detail')
        data = competitor.setdefault('data', {})

        data['tyre'] = detail.get('TyreType', data.get('tyre', ''))
        data['laps'] = detail.get('LastLap', data.get('laps', ''))
        data['s1'] = detail.get('LastSec1Time', data.get('s1', ''))
        data['s2'] = detail.get('LastSec2Time', data.get('s2', ''))
        data['s3'] = detail.get('LastSec3Time', data.get('s3', ''))
        data['bs1'] = detail.get('FastSec1Time', data.get('bs1', ''))
        data['bs2'] = detail.get('FastSec2Time', data.get('bs2', ''))
        data['bs3'] = detail.get('FastSec3Time', data.get('bs3', ''))
        data['last'] = detail.get('LastTime', data.get('last', ''))
        data['best'] = detail.get('FastTime', data.get('best', ''))

        data['gap_laps'] = detail.get('GapLeadLap', data.get('gap_laps', 0))
        data['int_laps'] = detail.get('GapNextLap', data.get('int_laps', 0))

        data['gap_time'] = detail.get('GapLeadTime', data.get('gap_time', 0))
        data['int_time'] = detail.get('GapNextTime', data.get('int_time', 0))

        data['pits'] = int(detail.get('PitStops', data.get('pits', 0)))

        data['state'] = detail.get('PitLaneFlag', data.get('state', ''))

    def handle_p(self, position):
        # <P L="1" LL="1" P="1" LP="1" C="50" D="1" T="0">
        # <D LT="0" L="1" I="380.2088" T="1517558793.5776" PN="1" I1="107.8246" I2="175.1511" S1="107.8246" S2="67.3265" S3="0.0000"
        # LL="2" P="N" LLP="1" LDC="0" LCD="1" FL="1" FTY="" FI="380.2088" FT="1517558793.5776" F1="107.8246" F2="175.1511" FS1="107.8246"
        # FS2="67.3265" FS3="181.4917" GL="0" GI="0.0000" GNL="0" GNI="0.0000" LGL="0" LGI="0.0000" LGNL="0" LGNI="0.0000" PS="1" PF=""
        # PI="0.0000" PT="44.2534" LP="6" TY="" TSL="0" />
        # </P>

        competitor = self._competitors[position.get('C')]
        pos = self._positions.setdefault(int(position.get('L')), {})

        pos['competitor'] = competitor
        pos['driver'] = competitor['drivers'][position.get('D')]

        detail = position.find('D')

        data = competitor.setdefault('data', {})

        data['tyre'] = detail.get('TY', data.get('tyre', ''))
        data['laps'] = detail.get('L', data.get('laps', ''))
        data['s1'] = detail.get('S1', data.get('s1', ''))
        data['s2'] = detail.get('S2', data.get('s2', ''))
        data['s3'] = detail.get('S3', data.get('s3', ''))
        data['bs1'] = detail.get('FS1', data.get('bs1', ''))
        data['bs2'] = detail.get('FS2', data.get('bs2', ''))
        data['bs3'] = detail.get('FS3', data.get('bs3', ''))
        data['last'] = detail.get('I', data.get('last', ''))
        data['best'] = detail.get('FI', data.get('best', ''))

        data['gap_laps'] = detail.get('LGL', data.get('gap_laps', 0))
        data['int_laps'] = detail.get('LGNL', data.get('int_laps', 0))

        data['gap_time'] = detail.get('LGI', data.get('gap_time', 0))
        data['int_time'] = detail.get('LGNI', data.get('int_time', 0))

        data['pits'] = int(detail.get('PS', data.get('pits', 0)))

        data['state'] = detail.get('PF', data.get('state', ''))

    def handle_counters(self, counters):
        raw_flag = counters.get('Status', None)
        if raw_flag:
            self._session['flag'] = map_flag(raw_flag)
        self._session['elapsed'] = (int(counters.get('Elapsed')), time.time())
        self._session['counter'] = (int(counters.get('Count')), counters.get('Type'))

    def handle_c(self, c):
        self._session['elapsed'] = (int(c.get('E')), time.time())
        try:
            C = int(c.get('C', 0))
        except ValueError:
            C = 0
        self._session['counter'] = (C, c.get('Y'))

    def handle_status(self, s):
        raw_flag = s.get('Status', None)
        if raw_flag:
            self._session['flag'] = map_flag(raw_flag)

    def handle_s(self, s):
        raw_flag = s.get('S', None)
        if raw_flag:
            self._session['flag'] = map_flag(raw_flag)

    # For our purposes, <Flag> / <F> are the same as <Status> / <S>.
    def handle_flag(self, flag):
        self.handle_status(flag)

    def handle_f(self, f):
        self.handle_s(f)


def _get_websocket_url(http_url):
    response = urllib.request.urlopen(http_url.rstrip('/'))
    ws_url = response.geturl()

    if '?' in ws_url:
        ws_url = ws_url[0:ws_url.index('?')]

    return re.sub('^https?:', 'ws:', ws_url)


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--url', help='HTTP URL to connect to (and derive WS URL from)')
    parser.add_argument('-w', '--ws', help='WebSocket URL to connect to')
    parser.add_argument('--host', help='Host to connect to for a TCP connection')
    parser.add_argument('-p', '--port', help='Port to connect to for a TCP connection', type=int)
    parser.add_argument('-n', '--name', help='Service name', default='Natsoft timing feed')

    return parser.parse_args(extra_args)


def map_car_state(state):
    mapp = {
        'P': 'PIT',
        'T': 'OUT',
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
        lap_float = float(laps)
        if lap_float == 1:
            return '1 lap'
        elif lap_float > 1:
            return '{:d1} laps'.format(laps)
        if float(time) > 0:
            return time
        return ''
    except ValueError:
        return time


def maybe_float(f):
    try:
        return float(f)
    except ValueError:
        return 0


class Service(lt_service):
    attribution = ['Natsoft', 'http://racing.natsoft.com.au']

    def __init__(self, args, extra):
        lt_service.__init__(self, args, extra)
        self._extra = parse_extra_args(extra)

        self._state = NatsoftState(self.log, self.onSessionChange)

        if self._extra.url:
            ws = _get_websocket_url(self._extra.url)
            self.log.info("Derived WebSocket URL {url}", url=ws)
            self._connectWS(ws)
        elif self._extra.ws:
            self.log.info("Using given WebSocket URL {url}", url=self._extra.ws)
            self._connectWS(self._extra.ws)
        elif self._extra.host and self._extra.port:
            self.log.info("Connecting to {host}:{port}", host=self._extra.host, port=self._extra.port)
            self._connectTCP(self._extra.host, self._extra.port)
        else:
            url = _get_websocket_url(self.getDefaultUrl())
            self.log.info("Using defaulted URL {url}", url=url)
            self._connectWS(url)

    def _connectWS(self, url):
            factory = ReconnectingWebSocketClientFactory(url)
            factory.protocol = create_ws_protocol(self.log, self._state.handle)
            connectWS(factory)

    def _connectTCP(self, host, port):
            factory = ReconnectingClientFactory()
            factory.protocol = create_tcp_protocol(self.log, self._state.handle)
            reactor.connectTCP(host, port, factory)

    def getDefaultUrl(self):
        raise Exception("Either HTTP or websocket URL, or host/port, must be specified")

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

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self._state.messages)
        ]

    def getRaceState(self):
        if not self._state.has_data:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0
                }
            }

        session = {
            'flagState': self._state._session['flag'].name.lower(),
        }

        if 'elapsed' in self._state._session:
            elapsed = self._state._session['elapsed']
            session['timeElapsed'] = int(elapsed[0] + (time.time() - elapsed[1]))

        if 'counter' in self._state._session:
            value, count_type = self._state._session['counter']
            if count_type[0] == 'L':
                    session['lapsRemain'] = max(0, value)
            if count_type[0] == 'T':
                if 'elapsed' in self._state._session:
                    session['timeRemain'] = max(value - (time.time() - elapsed[1]), 0)
                else:
                    session['timeRemain'] = value

        return {
            'cars': list(map(self.map_car, [value for (key, value) in sorted(self._state._positions.items())])),
            'session': session
        }

    def map_car(self, car):
        competitor = car['competitor']
        data = competitor['data']

        s1 = maybe_float(data.get('s1', 0))
        s2 = maybe_float(data.get('s2', 0))
        s3 = maybe_float(data.get('s3', 0))
        bs1 = maybe_float(data.get('bs1', 0))
        bs2 = maybe_float(data.get('bs2', 0))
        bs3 = maybe_float(data.get('bs3', 0))

        sbs = self._state._session.get('sb', [0, 0, 0, 0])

        s1_flag = 'sb' if s1 == sbs[1] else 'pb' if s1 == bs1 else ''
        s2_flag = 'sb' if s2 == sbs[2] else 'pb' if s2 == bs2 else ''
        s3_flag = 'sb' if s3 == sbs[3] else 'pb' if s3 == bs3 else ''

        try:
            last = float(data.get('last', 0))
        except ValueError:
            last = 0

        try:
            best = float(data.get('best', 0))
        except ValueError:
            best = 0

        if last == best:
            last_flag = 'sb-new' if last == sbs[0] and s3 > 0 else 'pb'
        else:
            last_flag = ''

        best_flag = 'sb' if best == sbs[0] else ''

        pits = data.get('pits', 0)

        return [
            competitor['number'],
            map_car_state(data.get('state', '')),
            competitor['category'],
            car['driver'],
            competitor['name'],
            competitor['vehicle'],
            data.get('laps', ''),
            map_tyre(data.get('tyre', '')),
            format_gap(data.get('gap_laps', 0), data.get('gap_time', 0)),
            format_gap(data.get('int_laps', 0), data.get('int_time', 0)),
            (s1, s1_flag) if s1 > 0 else '',
            (bs1, 'old') if bs1 > 0 else '',
            (s2, s2_flag) if s2 > 0 else '',
            (bs2, 'old') if bs2 > 0 else '',
            (s3, s3_flag) if s3 > 0 else '',
            (bs3, 'old') if bs3 > 0 else '',
            (last, last_flag) if last > 0 else '',
            (best, best_flag) if best > 0 else '',
            pits if pits > 0 else ''
        ]
