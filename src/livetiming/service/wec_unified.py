# -*- coding: utf-8 -*-
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, Fetcher, JSONFetcher
from twisted.internet import threads
from twisted.logger import Logger

import argparse
import wecapp
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from datetime import datetime
import time


def mapFlagState(params):
    if 'safety_car' in params and params['safety_car'] == "true":
        return FlagStatus.SC.name.lower()

    flagMap = {
        'green': FlagStatus.GREEN,
        'yellow': FlagStatus.YELLOW,
        'full_yellow': FlagStatus.FCY,
        'safety_car': FlagStatus.SC,
        'red': FlagStatus.RED,
        'chk': FlagStatus.CHEQUERED,
        'off': FlagStatus.NONE,
    }
    if 'status' in params:
        if params['status'].lower() in flagMap:
            return flagMap[params['status'].lower()].name.lower()
        Logger().warn("Unknown flag state {flag}", flag=params['status'])
    return 'none'


def mapCarState(rawState):
    stateMap = {
        'run': 'RUN',
        'in': 'PIT',
        'out': 'OUT',
        'ret': 'RET',
        '': 'N/S'
    }
    if rawState.lower() in stateMap:
        return stateMap[rawState.lower()]
    Logger().warn("Unknown car state {}".format(rawState))
    return rawState


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualifying", help="Use column set for aggregate qualifying", action="store_true")
    parser.add_argument("--session", help="Use given session ID instead of finding the current session")
    return parser.parse_known_args(extra_args)


def parseTime(formattedTime):
    if formattedTime == "" or formattedTime is None:
        return 0
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def get_session(session_id=None):
    if session_id:
        try:
            session_data = wecapp.get('http://pipeline-production.netcosports.com/wec/1/sessions/{}?resolve_ref=race_id'.format(session_id))
            return session_data.get('session', None)
        except HTTPError:
            Logger().warn("No session data found for ID {session_id}", session_id=session_id)
            return None
    else:
        init_dict = wecapp.get('http://pipeline-production.netcosports.com/wec/1/init?resolve_ref=session_id%2Crace_id')
        if 'init' in init_dict:
            init = init_dict['init']
            if 'session' in init:
                init['session']['race'] = init['race']
                return init['session']
    return None


class WECAppFetcher(Fetcher):
    def _defer(self):
        return threads.deferToThread(wecapp.get, self.url)


TIMING_URL = 'http://pipeline-production.netcosports.com/wec/1/live_standings/{}?resolve_ref=ranks.%24.participation_id%2Cranks.%24.participation.category_id%2Cranks.%24.participation.car_id%2Cranks.%24.participation.car.brand_id%2Cranks.%24.participation.team_id'


class Service(lt_service):
    attribution = ['WEC', 'http://www.fiawec.com/']

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)

        self._session_data = {}
        self._cars = {}

        self._last_timestamp = None
        self._last_retrieved = None
        self._app_fetcher = None
        self._web_fetcher = None

        self._parsed_extra_args = parse_extra_args(extra_args)[0]
        self.is_qualifying_mode = self._parsed_extra_args.qualifying

        if self.is_qualifying_mode:
            self.log.info("Starting up in QUALIFYING mode")

        self.description = "World Endurance Championship"

        def data_url():
            return "http://www.fiawec.com/assets/live/WEC/__data.json?_={}".format(int(1000 * time.time()))

        self._web_fetcher = JSONFetcher(data_url, self._handleWebData, 10)

        LoopingCall(self._get_current_session).start(60)

    def _get_current_session(self):
        self.log.debug("Updating WEC session...")
        self.session = get_session(self._parsed_extra_args.session)

        if self.session:
            self.log.info("Using session {sessionid}", sessionid=self.session['id'])
            new_description = u'{} - {}'.format(self.session['race']['name_en'], self.session['name_en'])
            if new_description != self.description:
                self.description = new_description
                self.publishManifest()
            if not self._app_fetcher:
                self._app_fetcher = WECAppFetcher(
                    TIMING_URL.format(self.session['id']),
                    self._handleAppData,
                    10
                )
                self._app_fetcher.start()
                reactor.callLater(5, self._web_fetcher.start)  # Stagger the retrieval

        else:
            self.log.info("No WEC session found!")
            if self._app_fetcher:
                self._app_fetcher.stop()
            if self._web_fetcher:
                self._web_fetcher.stop()

    def getName(self):
        return "WEC (gamma)"

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
            "Pressure",
            "Wind Speed",
            "Wind Direction",
            "Weather",
            "Updated",
            "Retrieved"
        ]

    def getPollInterval(self):
        return 5

    def _handleAppData(self, data):
        if 'live_standing' in data:
            ls = data['live_standing']
            try:
                ts = ls.get('original_timestamp', 0)
                pts = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")
                if not self._last_timestamp or pts > self._last_timestamp:
                    if 'ranks' in ls and len(ls['ranks']) > 0:

                        for car_data in ls['ranks']:
                            race_num = car_data['car_number']
                            car = self._cars.setdefault(race_num, {})

                            # These fields should always be set from either data source
                            car['rank'] = car_data['rank']
                            car['race_num'] = race_num
                            car['state'] = mapCarState(car_data['status'])
                            car['pos_in_class'] = car_data['rank_by_category']
                            car['s1'] = car_data['sectors']['0']['current'] or 0
                            car['bs1'] = car_data['sectors']['0']['best'] or 0
                            car['s2'] = car_data['sectors']['1']['current'] or 0
                            car['bs2'] = car_data['sectors']['1']['best'] or 0
                            car['s3'] = car_data['sectors']['2']['current'] or 0
                            car['bs3'] = car_data['sectors']['2']['best'] or 0

                            car['last_lap'] = parseTime(car_data['last_lap'])
                            car['best_lap'] = parseTime(car_data['best_lap'])

                            car['driver'] = car_data['current_pilot']
                            car['tyre'] = car_data['current_tyres']
                            car['lap'] = car_data['current_lap']
                            car['gap'] = car_data['gap']
                            car['int'] = car_data['gap_prev']
                            car['pits'] = car_data['pitstop']

                            # Quali fields
                            car['d1l1'] = parseTime(car_data.get('d1l1', ''))
                            car['d2l1'] = parseTime(car_data.get('d2l1', ''))
                            car['aggregate_best'] = min(car['d1l1'], car['d2l1'])
                            car['av_lap'] = car_data.get('av_time', None)

                            # These fields should not override data from the website if available
                            if 'category' not in car:
                                car['category'] = car_data['participation']['category']['name_id'].replace(" ", "")

                            if 'team' not in car:
                                car['team'] = car_data['participation']['team']['name_id']

                            if 'car' not in car:
                                brand = car_data['participation']['car'].get('brand', {})
                                model = car_data['participation']['car'].get('model', '')
                                car['car'] = u'{} {}'.format(brand.get('name_id', ''), model).strip()

                        sd = self._session_data

                        sd['trackTemp'] = ls['track_temp']
                        sd['airTemp'] = ls['air_temp']
                        sd['humidity'] = ls['humidity']
                        sd['windSpeed'] = ls['wind_speed']
                        sd['windDirection'] = ls['wind_direction']
                        sd['pressure'] = ls['pressure']
                        sd['weather'] = ls['weather']

                        sd['status'] = ls['status']
                        sd['safety_car'] = ls.get('safety_car', 0) == 1
                        sd['elapsed'] = ls.get('elapsed', 0)
                        sd['remain'] = self.session['duration_seconds'] - ls.get('elapsed', 0)

                        sd['alkamel_session_id'] = ls['alkamel_session_id']

                    self._last_timestamp = pts
                else:
                    self.log.debug("Not going backwards in time! Found {pts}, previously had {lts}", pts=pts, lts=self._last_timestamp)

                self._last_retrieved = datetime.utcnow()
            except ValueError:
                self.log.failure("Couldn't parse time. Sad times.")

    def _handleWebData(self, data):
        pass

    def getRaceState(self):

        cars = []
        session = {}

        bestLapsByClass = {}
        bestSectorsByClass = {1: {}, 2: {}, 3: {}}

        # First pass: identify fastest sectors/lap per class
        for car in self._cars.values():
            race_num = car['race_num']
            category = car['category']
            s1 = car['s1']
            bs1 = car['s1']
            s2 = car['s2']
            bs2 = car['s2']
            s3 = car['s3']
            bs3 = car['s3']

            if bs1 > 0 and (category not in bestSectorsByClass[1] or bestSectorsByClass[1][category][1] > bs1):
                bestSectorsByClass[1][category] = (race_num, bs1)
            if bs2 > 0 and (category not in bestSectorsByClass[2] or bestSectorsByClass[2][category][1] > bs2):
                bestSectorsByClass[2][category] = (race_num, bs2)
            if bs3 > 0 and (category not in bestSectorsByClass[3] or bestSectorsByClass[3][category][1] > bs3):
                bestSectorsByClass[3][category] = (race_num, bs3)

            if self.is_qualifying_mode:
                best_lap = car['aggregate_best']
            else:
                best_lap = car['best_lap']

            if best_lap > 0 and (category not in bestLapsByClass or bestLapsByClass[category][1] > best_lap):
                    bestLapsByClass[category] = (race_num, best_lap)

        # Second pass: assemble cars in order
        for car in sorted(self._cars.values(), key=lambda c: c['rank']):
            race_num = car['race_num']
            category = car['category']
            s1 = car['s1']
            bs1 = car['s1']
            s2 = car['s2']
            bs2 = car['s2']
            s3 = car['s3']
            bs3 = car['s3']
            last_lap = car['last_lap']

            def sector_time(sector):
                stime = car['s{}'.format(sector)]
                best = car['bs{}'.format(sector)]

                if stime == best:
                    if category in bestSectorsByClass[sector] and bestSectorsByClass[sector][category][0] == car_num:
                        flag = 'sb'
                    else:
                        flag = 'pb'
                else:
                    flag = ''

                return (stime if stime > 0 else '', flag)

            def bs_flag(bsector):
                if category in bestSectorsByClass[bsector] and bestSectorsByClass[bsector][category][0] == car_num:
                    return 'sb'
                return 'old'

            common_cols = [
                race_num,
                car['state'],
                category,
                car['pos_in_class'],
                car['team'],
                car['driver'],
                car['car'],
                car['tyre'],
                car['lap'],
                car['gap'],
                car['int'],
                sector_time(1),
                (bs1 if bs1 > 0 else '', bs_flag(1)),
                sector_time(2),
                (bs2 if bs2 > 0 else '', bs_flag(2)),
                sector_time(3),
                (bs3 if bs3 > 0 else '', bs_flag(3))
            ]

            we_have_fastest = (category in bestLapsByClass and bestLapsByClass[category][0] == car_num)
            fastest = bestLapsByClass[category][1] if category in bestLapsByClass else None
            last_flag = 'sb-new' if we_have_fastest and last_lap == fastest else 'pb' if last_lap == best_lap else ''

            if self.is_qualifying_mode:
                d1_lap = car['d1l1']
                d2_lap = car['d2l1']
                best_lap = car['aggregate_best']
                av_lap = car['av_time']

                d1_flag = 'sb' if we_have_fastest and d1_lap == fastest else 'sb' if d1_lap == best_lap else ''
                d2_flag = 'sb' if we_have_fastest and d2_lap == fastest else 'sb' if d2_lap == best_lap else ''

                cars.append(common_cols + [
                    (last_lap if last_lap > 0 else '', last_flag),
                    (d1_lap or '', d1_flag),
                    (d2_lap or '', d2_flag),
                    (av_lap or '', '')
                ])
            else:
                best_lap = parseTime(car['best_lap'])
                cars.append(common_cols + [
                    (last_lap if last_lap > 0 else '', last_flag),
                    (best_lap if best_lap > 0 else '', 'sb' if we_have_fastest and best_lap == fastest else ''),
                    car['pits']
                ])

        session['flagState'] = mapFlagState(self._session_data)

        delta = (datetime.utcnow() - self._last_timestamp).total_seconds()

        session['timeElapsed'] = self._session_data['elapsed'] + delta
        session['timeRemain'] = self._session_data['remain'] - delta
        session['trackData'] = [
            u"{}°C".format(self._session_data['trackTemp']),
            u"{}°C".format(self._session_data['airTemp']),
            "{}%".format(self._session_data['humidity']),
            "{}mbar".format(self._session_data['pressure']),
            "{}kph".format(self._session_data['windSpeed']),
            u"{}°".format(self._session_data['windDirection']),
            self._session_data['weather'].replace('_', ' ').title(),
            self._last_timestamp.strftime("%H:%I:%S") if self._last_timestamp else '',
            self._last_retrieved.strftime("%H:%I:%S") if self._last_retrieved else ''
        ]

        return {
            "cars": cars,
            "session": session
        }
