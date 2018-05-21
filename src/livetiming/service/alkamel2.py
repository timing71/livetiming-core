from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.racing import Stat
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.utils.meteor import MeteorClient, DDPProtoclFactory


class AlkamelV2Client(MeteorClient):
    def __init__(self, feed_name):
        MeteorClient.__init__(self)

        self._current_session_id = None

        self._feed_name = feed_name
        self._factory = ReconnectingWebSocketClientFactory('wss://livetiming.alkamelsystems.com/sockjs/261/t48ms2xd/websocket')
        self._factory.protocol = DDPProtoclFactory(self)
        connectWS(self._factory)

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

        self.subscribe('sessions', [feeds[0]['sessions']], self.recv_sessions)
        self.subscribe('sessionInfo', [feeds[0]['sessions']], self.recv_session_info)

    def recv_sessions(self, _):
        pass

    def recv_session_info(self, _):
        sessionInfo = self.find('session_info')

        live_sessions = [s for s in sessionInfo if not s.get('info', {}).get('closed', False)]
        if len(live_sessions) == 0:
            self.log.warn("No live sessions detected, instead arbitrarily using {sid}", sid=sessionInfo[0]['session'])
            self.set_session(sessionInfo[0])
        else:
            self.set_session(live_sessions[0])

    def set_session(self, session_info):
        self.log.info("Session info chosen: {info}", info=session_info)
        self._current_session_id = session_info['session']
        self.subscribe('entry', [self._current_session_id])
        self.subscribe('standings', [self._current_session_id])
        self.subscribe('sessionStatus', [self._current_session_id])


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


class Service(lt_service):
    attribution = ['Al Kamel Systems', 'http://www.alkamelsystems.com/']

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)

        self._client = AlkamelV2Client('fiaformulae')

    def getName(self):
        return "Al Kamel v2"

    def getDefaultDescription(self):
        return 'Testing'

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

    def getRaceState(self):
        # print self._client.collection_data
        return {
            'session': {
                'flagState': 'none'
            },
            'cars': self._map_standings()
        }

    def _map_standings(self):
        standings_data = self._client.find_one('standings', {'session': self._client._current_session_id})
        entries_data = self._client.find_one('session_entry', {'session': self._client._current_session_id})

        if standings_data and entries_data:
            standings = standings_data.get('standings', {}).get('standings', {})
            entries = entries_data.get('entry', {})

            if standings and entries:
                cars = []
                for position in sorted(map(int, standings.keys())):
                    data = standings[str(position)]
                    if 'data' in data:
                        standing_data = data['data'].split(";")
                        race_num = standing_data[1]
                        entry = entries.get(race_num, {})

                        sectors = parse_sectors(data.get('currentSectors', ';;;;;;'))

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
                            'gap',
                            'int',
                            sectors[1],
                            sectors[2],
                            sectors[3],
                            (data.get('lastLapTime', 0) / 1000.0, 'pb' if data.get('isLastLapBestPersonal', False) else ''),
                            (data.get('bestLapTime', 0) / 1000.0, ''),
                            standing_data[5]
                        ])

                return cars

        return []
