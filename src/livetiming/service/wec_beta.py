# -*- coding: utf-8 -*-
from livetiming.analysis.driver import StintLength
from livetiming.analysis.lapchart import LapChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.analysis.session import Session
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, Fetcher
from twisted.logger import Logger

import argparse
import wecapp


def mapFlagState(params):
    if 'safetycar' in params and params['safetycar'] == "true":
        return FlagStatus.SC.name.lower()

    flagMap = {
        'green': FlagStatus.GREEN,
        'yellow': FlagStatus.YELLOW,
        'full_yellow': FlagStatus.FCY,
        'red': FlagStatus.RED,
        'chk': FlagStatus.CHEQUERED,
        'off': FlagStatus.NONE
    }
    if 'status' in params and params['status'].lower() in flagMap:
        return flagMap[params['status'].lower()].name.lower()
    Logger().warn("Unknown flag state {flag}", flag=params.get('status', None))
    return 'none'


def mapCarState(rawState):
    stateMap = {
        'run': 'RUN',
        'in': 'PIT',
        'out': 'OUT'
    }
    if rawState in stateMap:
        return stateMap[rawState]
    Logger().warn("Unknown car state {}".format(rawState))
    return rawState


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualifying", help="Use column set for aggregate qualifying", action="store_true")
    return parser.parse_known_args(extra_args)


def get_session():
    init_dict = wecapp.get('http://pipeline-production.netcosports.com/wec/1/init?resolve_ref=session_id%2Crace_id')
    if 'init' in init_dict:
        init = init_dict['init']
        if 'session' in init:
            init['session']['race'] = init['race']
            return init['session']
    return None


class WECFetcher(Fetcher):
    def _defer(self):
        return wecapp.get(self.url)


class Service(lt_service):
    log = Logger()

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)
        self.params = {}
        self.entries = []
        self.latest_seen_timestamp = None

        self.is_qualifying_mode = parse_extra_args(extra_args)[0].qualifying

        if self.is_qualifying_mode:
            self.log.info("Starting up in QUALIFYING mode")

        self.description = "World Endurance Championship"
        self.session = get_session()

        if self.session:
            self.description = u'{} - {}'.format(self.session['race']['name_en'], self.session['name_en'])
            f = WECFetcher(
                'http://pipeline-production.netcosports.com/wec/1/live_standings/{}?resolve_ref=ranks.%24.participation_id%2Cranks.%24.participation.category_id%2Cranks.%24.participation.car_id%2Cranks.%24.participation.car.brand_id%2Cranks.%24.participation.team_id'.format(self.session['id']),
                self._handleData,
                10
            )
            f.start()

    def getName(self):
        return "WEC (beta)"

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        common_cols = [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.POS_IN_CLASS,
            Stat.TEAM,
            Stat.DRIVER,
            Stat.CAR,
            Stat.TYRE,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.BS1,
            Stat.S2,
            Stat.BS2,
            Stat.S3,
            Stat.BS3,
            Stat.LAST_LAP
        ]
        if self.is_qualifying_mode:
            return common_cols + [
                Stat.DRIVER_1_BEST_LAP,
                Stat.DRIVER_2_BEST_LAP,
                Stat.AGGREGATE_BEST_LAP
            ]
        else:
            return common_cols + [
                Stat.BEST_LAP,
                Stat.PITS
            ]

    def getTrackDataSpec(self):
        return [
            "Track Temp",
            "Air Temp",
            "Humidity",
            "Wind Speed",
            "Wind Direction",
            "Weather"
        ]

    def getPollInterval(self):
        return None  # We handle this ourselves in _handleData - otherwise data might lag by 2*10 seconds :(

    def getAnalysisModules(self):
        return [
            Session,
            LapChart,
            EnduranceStopAnalysis,
            StintLength
        ]

    def _handleData(self, data):
        if 'live_standing' in data:
            if 'ranks' in data['live_standing']:
                self.entries = data['live_standing']['ranks'][:]
                del data['live_standing']['ranks']
                self.params = data['live_standing']

        self._updateAndPublishRaceState()

    def getRaceState(self):
        cars = []
        session = {}

        bestLapsByClass = {}
        bestSectorsByClass = {1: {}, 2: {}, 3: {}}

        for car in self.entries:
            category = car['participation']['category']['name_id']
            last_lap = car['last_lap']
            race_num = car['participation']['number']

            s1 = car['sectors']['0']['current'] or 0
            bs1 = car['sectors']['0']['best'] or 0
            s2 = car['sectors']['1']['current'] or 0
            bs2 = car['sectors']['1']['best'] or 0
            s3 = car['sectors']['2']['current'] or 0
            bs3 = car['sectors']['2']['best'] or 0

            if bs1 > 0 and (category not in bestSectorsByClass[1] or bestSectorsByClass[1][category][1] > bs1):
                bestSectorsByClass[1][category] = (race_num, bs1)
            if bs2 > 0 and (category not in bestSectorsByClass[2] or bestSectorsByClass[2][category][1] > bs2):
                bestSectorsByClass[2][category] = (race_num, bs2)
            if bs3 > 0 and (category not in bestSectorsByClass[3] or bestSectorsByClass[3][category][1] > bs3):
                bestSectorsByClass[3][category] = (race_num, bs3)

            common_cols = [
                race_num,
                mapCarState(car['status']),
                category,
                car['rank_by_category'],
                car['participation']['team']['name_id'],
                car['current_pilot'],
                u'{} {}'.format(car['participation']['car']['brand']['name_id'], car['participation']['car']['model'] if 'model' in car['participation']['car'] else ''),
                car['current_tyres'],
                car['current_lap'],
                car['gap'],
                car['gap_prev'],
                (s1, 'pb' if s1 == bs1 else ''),
                (bs1, 'old' if s1 != bs1 else ''),
                (s2, 'pb' if s2 == bs2 else ''),
                (bs2, 'old' if s2 != bs2 else ''),
                (s3, 'pb' if s3 == bs3 else ''),
                (bs3, 'old' if s3 != bs3 else '')
            ]

            if self.is_qualifying_mode:
                d1_lap = car['d1l1']
                d2_lap = car['d2l1']
                best_lap = min(d1_lap, d2_lap)
                av_lap = car['av_time']

                cars.append(common_cols + [
                    (last_lap, 'pb' if last_lap == best_lap else ''),
                    (d1_lap or '', 'pb' if best_lap == d1_lap else ''),
                    (d2_lap or '', 'pb' if best_lap == d2_lap else ''),
                    (av_lap or '', '')
                ])
            else:
                best_lap = car['best_lap']
                cars.append(common_cols + [
                    (last_lap, 'pb' if last_lap == best_lap else ''),
                    (best_lap, ''),
                    car['pitstop']
                ])

            if best_lap > 0 and (category not in bestLapsByClass or bestLapsByClass[category][1] > best_lap):
                    bestLapsByClass[category] = (race_num, best_lap)

        for car in cars:
            # Second pass to highlight sb/sb-new
            car_num = car[0]
            category = car[2]

            # Best lap
            if category in bestLapsByClass and bestLapsByClass[category][0] == car_num:
                best_lap_time = bestLapsByClass[category][1]
                if self.is_qualifying_mode:
                    if car[17][0] == best_lap_time:  # D1L1
                        car[17] = (car[17][0], 'sb')
                    elif car[18][0] == best_lap_time:  # D2L1
                        car[18] = (car[18][0], 'sb')
                else:
                    car[17] = (car[17][0], 'sb')
                if car[16][0] == best_lap_time:
                    car[16] = (car[16][0], 'sb-new')

            # Best sectors
            if category in bestSectorsByClass[1] and bestSectorsByClass[1][category][0] == car_num:
                car[11] = (car[11][0], 'sb')
                if car[10][0] == car[11][0]:
                    car[10] = (car[10][0], 'sb')
            if category in bestSectorsByClass[2] and bestSectorsByClass[2][category][0] == car_num:
                car[13] = (car[13][0], 'sb')
                if car[12][0] == car[13][0]:
                    car[12] = (car[12][0], 'sb')
            if category in bestSectorsByClass[3] and bestSectorsByClass[3][category][0] == car_num:
                car[15] = (car[15][0], 'sb')
                if car[14][0] == car[15][0]:
                    car[14] = (car[14][0], 'sb')

        session['flagState'] = mapFlagState(self.params)

        session['timeElapsed'] = self.params['elapsed'] if 'elapsed' in self.params else None
        session['timeRemain'] = self.session['duration_seconds'] - self.params.get('elapsed', 0)

        if 'track_temp' in self.params:
            session['trackData'] = [
                u"{}°C".format(self.params['track_temp']),
                u"{}°C".format(self.params['air_temp']),
                "{}%".format(self.params['humidity']),
                "{}kph".format(self.params['wind_speed']),
                u"{}°".format(self.params['wind_direction']),
                self.params['weather'].replace('_', ' ').title()
            ]

        return {
            "cars": cars,
            "session": session
        }
