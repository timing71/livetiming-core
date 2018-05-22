from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from datetime import datetime
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.utils.meteor import MeteorClient, DDPProtoclFactory


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
            self.session_status_timestamp = datetime.utcnow()

        self.on_collection_change('session_info', self.recv_session_info)
        self.on_collection_change('session_status', setSessionStatusTimestamp)

    def onConnect(self):
        self.subscribe('livetimingFeed', [self._feed_name], self.recv_feeds)
        self.subscribe('sessionClasses', [None])
        self.subscribe('trackInfo', [None])

    def recv_feeds(self, _):
        feeds = self.find('feeds')
        self.log.debug("Found feeds: {feeds}", feeds=map(lambda f: f['name'], feeds))

        if len(feeds) == 0:
            raise 'No valid feeds found'
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
        self.session_type = session_info.get('type', 'UNKNOWN')
        self.subscribe('entry', [self._current_session_id])
        self.subscribe('standings', [self._current_session_id])
        self.subscribe('sessionStatus', [self._current_session_id])

        self.emit('session_change', self.find_one('sessions', {'_id': self._current_session_id}), session_info)


def parse_sectors(sectorString):
    sectors = {}
    parts = sectorString.split(';')

    for i in range(3):
        idx = 6 * i
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
            flag = ''

        sectors[sector] = (time / 1000.0, flag)

    return sectors


CAR_TRACK_STATES = {
    'BOX': 'PIT',
    'OUT_LAP': 'OUT',
    'STOPPED': 'STOP'
}

CAR_STATES = {
    'RETIRED': 'RET',
    'NOT_CLASSIFIED': 'N/C',
    'NOT_STARTED': 'N/S',
    'DISQUALIFIED': 'DSQ',
    'EXCLUDED': 'DSQ'
}


# e.lookup("status"), e.lookup("trackStatus"), e.lookup("isRunning"), e.lookup("isCheckered"), e.lookup("isSessionClosed"), false
def map_car_state(status, trackStatus, isRunning, isCheckered):
    if 'CLASSIFIED' == status.upper():
        if isCheckered:
            return 'FIN'
        if isRunning:
            return 'RUN'
    if trackStatus.upper() in CAR_TRACK_STATES:
        return CAR_TRACK_STATES[trackStatus.upper()]
    if status.upper() in CAR_STATES:
        return CAR_STATES[status.upper()]
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
        elif n['currentLoops'][t]:
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
    return n['currentLapStartTime'] + n['currentLoops'][t]


def calculate_gap(first, second):
    if not first:
        return ''

    if not second.get('isRunning', False):
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
    s = second['currentLapStartTime'] + (0 if a < 0 else second['currentLoops'][a])
    o = len(first['currentLoops']) - 1
    l = e(a, first, o)

    return abs(s - l) / 1000.0


def calculate_practice_gap(first, second):
    if first and second and first.get('bestLapTime', 0) > 0 and second.get('bestLapTime', 0) > 0:
        return max(0, second['bestLapTime'] - first['bestLapTime'])
    return ''


class Service(lt_service):
    attribution = ['Al Kamel Systems', 'http://www.alkamelsystems.com/']

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)
        self._prev_session_id = None
        self._client = AlkamelV2Client('fiaformulae')
        self._client.on('session_change', self.on_session_change)

        self._name = 'Al Kamel Timing'
        self._description = ''

    def getName(self):
        return self._name

    def getDefaultDescription(self):
        return self._description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
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

    def getRaceState(self):
        # print self._client.collection_data
        return {
            'session': self._map_session(),
            'cars': self._map_standings()
        }

    def _map_standings(self):
        gap_func = calculate_gap if self._client.session_type == 'RACE' else calculate_practice_gap
        standings_data = self._client.find_one('standings', {'session': self._client._current_session_id})
        entries_data = self._client.find_one('session_entry', {'session': self._client._current_session_id})

        if standings_data and entries_data:
            standings = standings_data.get('standings', {}).get('standings', {})
            entries = entries_data.get('entry', {})

            if standings and entries:
                cars = []
                prev_car = None
                lead_car = None
                for position in sorted(map(int, standings.keys())):
                    data = standings[str(position)]
                    if 'data' in data:
                        standing_data = data['data'].split(";")
                        race_num = standing_data[1]
                        entry = entries.get(race_num, {})

                        sectors = parse_sectors(data.get('currentSectors', ';;;;;;'))

                        data_with_loops = {
                            'currentLoops': _parse_loops(data.get('currentLoopSectors')),
                            'previousLoops': _parse_loops(data.get('previousLoopSectors')),
                            'currentLapStartTime': int(standing_data[7]) or 0,
                            'currentLapNumber': int(standing_data[9]) or 0,
                            'laps': int(standing_data[4]) or 0
                        }
                        data_with_loops.update(data)

                        status = standing_data[2]
                        trackStatus = standing_data[8]

                        state = map_car_state(status, trackStatus, data.get('isRunning', False), data.get('isCheckered', False))

                        cars.append([
                            race_num,
                            state,
                            u"{}, {}".format(entry.get('lastname', ''), entry.get('firstname', '')),
                            entry.get('team', ''),
                            entry.get('vehicle', ''),
                            standing_data[4],
                            gap_func(lead_car, data_with_loops),
                            gap_func(prev_car, data_with_loops),
                            sectors[1],
                            sectors[2],
                            sectors[3],
                            (data.get('lastLapTime', 0) / 1000.0, 'pb' if data.get('isLastLapBestPersonal', False) else ''),
                            (data.get('bestLapTime', 0) / 1000.0, ''),
                            standing_data[5]
                        ])

                    prev_car = data_with_loops
                    if not lead_car:
                        lead_car = data_with_loops

                return cars

        return []

    def _map_session(self):
        result = {'flagState': 'none', 'timeElapsed': 0}

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
                now = datetime.utcnow()

                if sessionRunning and self._client.session_status_timestamp:
                    delta = (now - self._client.session_status_timestamp).total_seconds()
                else:
                    delta = 0

                if status.get('isForcedByTime', False) or status.get('finalType') == "BY_TIME" or status.get('finalType') == "BY_TIME_PLUS_LAPS":
                    if sessionRunning:
                        result['timeRemain'] = finalTime - (startTime - stoppedSeconds) - delta
                    else:
                        result['timeRemain'] = finalTime - (stopTime - startTime - stoppedSeconds)
                else:
                    result['lapsRemain'] = max(0, status.get('finalLaps', 0) - status.get('elapsedLaps', 0))

                if startTime > 0:
                    startTimestamp = datetime.utcfromtimestamp(startTime)
                    if stopTime > 0:
                        result['timeElapsed'] = (stopTime - startTime)
                    else:
                        result['timeElapsed'] = (now - startTimestamp).total_seconds() - status.get('stoppedSeconds', 0) + delta

        return result
