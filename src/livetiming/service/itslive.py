from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.web import client

import argparse
import requests
import simplejson
import time
import treq
import urllib2


client.HTTPClientFactory.noisy = False

API_ROOT = 'https://api-live.its-live.net/v1'


def json_get(url):
    print "Getting {}".format(url)
    try:
        return simplejson.load(urllib2.urlopen(url))
    except simplejson.JSONDecodeError:
        return None


def get_current_season(series):
    seasons = json_get('{}/Events/ListSeasons/{}'.format(
        API_ROOT,
        series
    ))
    return seasons[-1]


def get_current_event(series, season):
    events = json_get('{}/Events/ListEvents/{}/{}'.format(
        API_ROOT,
        series,
        season
    ))

    now = time.time()
    current = [ev for ev in events if ev['begin_epoch'] <= now and ev['end_epoch'] >= now]

    if current:
        return current[0]
    else:
        print 'No current event, using latest one.'
        return events[-1]


def get_current_session(series, season, event):
    sessions = json_get('{}/Session/ListSessions/{}/{}/{}'.format(
        API_ROOT,
        series,
        season,
        event
    ))

    now = time.time()
    current = [s for s in sessions if s['start_epoch'] <= now and ('end_epoch' not in s or s['end_epoch'] >= now)]

    if current:
        return current[0]
    else:
        print "No current session, using most recent one."
        return sessions[-1]


@inlineCallbacks
def json_post(url, body):
    response = yield treq.post(
        url,
        json=body,
        headers={
            'Content-Type': 'application/json'
        }
    )

    body = yield treq.json_content(response)
    returnValue(body)


@inlineCallbacks
def get_session_standings(ssid, start_id):
    body = {
        'startPos': 0,
        'endPos': 1000000,
        'startId': start_id,
        'ssid': ssid
    }

    result = yield json_post(
        '{}/Session/GetRankingWithBestOfAll'.format(API_ROOT),
        body
    )
    returnValue(result)


def get_session_data(ssid):
    return json_post(
        '{}/Session/GetLastRaceInfo'.format(API_ROOT),
        ssid
    )


def get_last_message(ssid):
    return json_post(
        '{}/Session/GetLastMsg'.format(API_ROOT),
        ssid
    )


def parseExtraArgs(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", help="Series ID", required=True)
    a, _ = parser.parse_known_args(extra_args)
    return a


STATE_IMAGES_MAP = {
    '_CheckeredFlag': 'FIN',
    '_PitIn': 'PIT',
    '_PitOut': 'OUT'
}

STATE_NUMBERS_MAP = {
    1: 'LC',
    2: 'N/C',
    3: 'NT',
    4: 'LT1',
    5: 'N/S',
    6: 'N/C',
    7: 'N/C',
    8: 'N/C',
    9: 'DNF',
    10: 'RET',
    11: 'DSQ',
    12: 'DSQ'
}


def map_car_state(car):
    state = car['status']
    state_img = car['status_img']

    if state_img in STATE_IMAGES_MAP:
        return STATE_IMAGES_MAP[state_img]
    return STATE_NUMBERS_MAP.get(state, 'RUN')


def map_sector(car, sector, boa):
    last = car['inter_{}'.format(sector)]
    best = car['best_inter_{}'.format(sector)]
    sb = boa[sector]

    last_flag = ''
    if last == best:
        if last == sb:
            last_flag = 'sb'
        else:
            last_flag = 'pb'

    best_flag = 'sb' if best == sb else 'old'

    return [
        (last / 1000.0 if last else '', last_flag),
        (best / 1000.0 if best else '', best_flag)
    ]


def map_laptimes(car, boatime):
    last = car['lap_time']
    best = car['best_time']

    last_flag = ''
    if last == best:
        if last == boatime:
            last_flag = 'sb-new'
        else:
            last_flag = 'pb'

    best_flag = 'sb' if boatime == best else 'old'

    return [
        (last / 1000.0 if last and last > 0 else '', last_flag),
        (best / 1000.0 if best and best > 0 else '', best_flag)
    ]


def map_car(boa, boatime):
    def inner(car):
        return [
            car['number'],
            map_car_state(car),
            car['driver_names'][car['current_driver']],
            car['team'],
            car['vehicle'],
            car['total_lap'],
            car['gap_first'],
            car['gap_prev']
        ] + \
            map_sector(car, 1, boa) + \
            map_sector(car, 2, boa) + \
            map_sector(car, 3, boa) + \
            map_sector(car, 4, boa) + \
            map_laptimes(car, boatime) + [
            car['total_pit_stop']
        ]
    return inner


SESSION_FLAG_MAP = {
    'STOP': FlagStatus.CHEQUERED.name,
    'CHECKERED FLAG': FlagStatus.CHEQUERED.name,
    'GREEN FLAG': FlagStatus.GREEN.name,
    'RED FLAG': FlagStatus.RED.name,
    'SAFETY CAR': FlagStatus.SC.name,
    'SLOW ZONE': FlagStatus.SLOW_ZONE.name,
    'YELLOW FLAG': FlagStatus.YELLOW.name
}


def map_session(session):
    now = time.time()

    offset = now - session.get('last_update', 0)

    session = {
        'timeElapsed': session.get('elapsed_time', 0) + offset,
        'timeRemain': max(0, session.get('remaining_time', 0) - offset),
        'flagState': SESSION_FLAG_MAP.get(session.get('race_flag'), 'none').lower(),
    }

    laps_remaining = session.get('remaining_lap', 0)
    if laps_remaining > 0:
        session['lapsRemain'] = laps_remaining

    return session


class Service(lt_service):
    attribution = ['ITS Chrono', 'https://www.its-live.net']

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)

        self.extra_args = parseExtraArgs(extra_args)

        self._session = {}
        self._start_id = 0
        self._standingsData = {
            'boa': [None] * 8,
            'sboa': [None] * 8,
            'boaTime': None,
            'cars': {}
        }
        self._messages = []
        self._lastMessage = 0

        self._find_session(self.extra_args.series)

        LoopingCall(self._fetch_ranking_data).start(1)
        LoopingCall(self._fetch_session_data).start(1)
        LoopingCall(self._fetch_last_message).start(1)

    @inlineCallbacks
    def _fetch_ranking_data(self):
        data = yield get_session_standings(self._ssid, self._start_id)

        self._standingsData['boa'] = data['boa']
        self._standingsData['sboa'] = data['sboa']
        self._standingsData['boaTime'] = data['boaTime']

        for car in data['ranking']:
            id = car['competitor_id']
            self._standingsData['cars'].setdefault(id, {}).update(car)
            self._start_id = max(self._start_id, car.get('data_id', 0))

    @inlineCallbacks
    def _fetch_session_data(self):
        data = yield get_session_data(self._ssid)
        self._session.update(data)

    @inlineCallbacks
    def _fetch_last_message(self):
        data = yield get_last_message(self._ssid)

        if data.get('data_id', 0) > self._lastMessage:
            self._messages.append(data['msg'][9:])
            self._lastMessage = data['epoch_ms']

    def _find_session(self, series):
        season = get_current_season(series)
        if season:
            event = get_current_event(series, season['name'])
            if event:
                session = get_current_session(series, season['name'], event['event_id'])
                self.log.info("Found session: {session}", session=session)
                self._session = session
                self._ssid = {
                    'cs_id': series,
                    'season': season['name'],
                    'event_id': event['event_id'],
                    'session_id': session['session_id']
                }

    def getName(self):
        return self._session.get('folder_name', 'ITS Chrono')

    def getDefaultDescription(self):
        return self._session.get('race_name', '')

    def getPollInterval(self):
        return 1

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

    def getRaceState(self):
        return {
            'cars': map(
                map_car(
                    self._standingsData.get('boa'),
                    self._standingsData.get('boaTime')
                ),
                sorted(
                    self._standingsData['cars'].values(),
                    key=lambda c: c['pos']
                )
            ),
            'session': map_session(self._session)
        }

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self._messages)
        ]
