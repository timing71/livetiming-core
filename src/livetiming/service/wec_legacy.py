# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, JSONFetcher
from simplejson.scanner import JSONDecodeError
from twisted.logger import Logger

import re
import simplejson
import time
import argparse


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
    if 'racestate' in params and params['racestate'].lower() in flagMap:
        return flagMap[params['racestate'].lower()].name.lower()
    Logger().warn("Unknown flag state {flag}", flag=params.get('racestate', None))
    return 'none'


def mapCarState(rawState):
    stateMap = {
        'Run': 'RUN',
        'In': 'PIT',
        'Out': 'OUT',
        'Ret': 'RET'
    }
    if rawState in stateMap:
        return stateMap[rawState]
    Logger().warn("Unknown car state {}".format(rawState))
    return rawState


def parseTime(formattedTime):
    if formattedTime == "" or formattedTime is None:
        return ''
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


SESSION_TIME_REGEX = re.compile("(?P<hours>[0-9]{1-2}) : (?P<minutes>[0-9]{2}) : (?P<seconds>[0-9]{2})")


def parseSessionTime(formattedTime):
    m = SESSION_TIME_REGEX.match(formattedTime)
    if m:
        return (3600 * int(m.group('hours'))) + (60 * int(m.group('minutes'))) + int(m.group('seconds'))
    try:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        if formattedTime.startswith("24"):
            return 86400
        else:
            return formattedTime


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualifying", help="Use column set for aggregate qualifying", action="store_true")
    return parser.parse_known_args(extra_args)


class Service(lt_service):
    log = Logger()
    attribution = ['WEC', 'http://www.fiawec.com/']
    auto_poll = False  # We handle this ourselves in _handleData - otherwise data might lag by 2*10 seconds :(

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)
        self.params = {}
        self.entries = []
        self.latest_seen_timestamp = None

        self.messages = []
        self.prevRaceControlMessages = []

        self.is_qualifying_mode = parse_extra_args(extra_args)[0].qualifying

        if self.is_qualifying_mode:
            self.log.info("Starting up in QUALIFYING mode")

        self.description = "World Endurance Championship"
        self.session_id = None

        def data_url():
            return "https://storage.googleapis.com/fiawec-prod/assets/live/WEC/__data.json?_t={}".format(int(1000 * time.time()))

        fetcher = JSONFetcher(data_url, self._handleData, 10)
        fetcher.start()

        self.col_map = {}
        for idx, stat in enumerate(self.getColumnSpec()):
            self.col_map[stat] = idx

    def getName(self):
        return "WEC"

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
            Stat.LAST_LAP  # old 16
        ]
        if self.is_qualifying_mode:
            return common_cols + [
                Stat.DRIVER_1_BEST_LAP,  # 17
                Stat.DRIVER_2_BEST_LAP,  # 18
                Stat.AGGREGATE_BEST_LAP  # 19
            ]
        else:
            return common_cols + [
                Stat.BEST_LAP,  # 17
                Stat.PITS  # 18
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
        return 10

    def _data_is_newer(self, params):
        if self.latest_seen_timestamp is None:
            return True
        if "timestamp" not in params:
            return True
        return params["timestamp"] > self.latest_seen_timestamp

    def _handleData(self, data):
        if "params" in data:
            params = data['params']
            if self._data_is_newer(params):
                self.params = params
                if 'eventName' in self.params and self.params['eventName'] != self.description:
                    self.description = self.params['eventName']
                    self.publishManifest()
                    self.analyser.reset()
                if "sessionId" in params and params['sessionId'] != self.session_id:
                    self.session_id = params['sessionId']
                    self.analyser.reset()

                self.latest_seen_timestamp = self.params.get("timestamp", None)

            if "entries" in data:
                self.entries = data['entries']
            self._updateAndPublishRaceState()

    def getRaceState(self):
        cars = []
        session = {}

        bestLapsByClass = {}
        bestSectorsByClass = {1: {}, 2: {}, 3: {}}

        for car in self.entries:
            category = car['category']
            last_lap = parseTime(car['lastlap'])

            s1 = parseTime(car['currentSector1'])
            bs1 = parseTime(car['bestSector1'])
            s2 = parseTime(car['currentSector2'])
            bs2 = parseTime(car['bestSector2'])
            s3 = parseTime(car['currentSector3'])
            bs3 = parseTime(car['bestSector3'])

            state = mapCarState(car['state'])

            if bs1 > 0 and (category not in bestSectorsByClass[1] or bestSectorsByClass[1][category][1] > bs1):
                bestSectorsByClass[1][category] = (car['number'], bs1)
            if bs2 > 0 and (category not in bestSectorsByClass[2] or bestSectorsByClass[2][category][1] > bs2):
                bestSectorsByClass[2][category] = (car['number'], bs2)
            if bs3 > 0 and (category not in bestSectorsByClass[3] or bestSectorsByClass[3][category][1] > bs3):
                bestSectorsByClass[3][category] = (car['number'], bs3)

            common_cols = [
                car['number'],
                state,
                category,
                car['categoryPosition'],
                car['team'],
                car['driver'],
                car['car'],
                car['tyre'],
                car['lap'],
                car['gap'],
                car['gapPrev'],
                (s1, 'pb' if s1 == bs1 else ''),
                (bs1, 'old' if s1 != bs1 else ''),
                (s2, 'pb' if s2 == bs2 else ''),
                (bs2, 'old' if s2 != bs2 else ''),
                (s3, 'pb' if s3 == bs3 else ''),
                (bs3, 'old' if s3 != bs3 else '')
            ]

            if self.is_qualifying_mode:
                d1_lap = parseTime(car['d1l1'])
                d2_lap = parseTime(car['d2l1'])
                best_lap = min(d1_lap, d2_lap)
                av_lap = parseTime(car['av_time'])

                cars.append(common_cols + [
                    (last_lap, 'pb' if last_lap == best_lap else ''),
                    (d1_lap or '', 'pb' if best_lap == d1_lap else ''),
                    (d2_lap or '', 'pb' if best_lap == d2_lap else ''),
                    (av_lap or '', '')
                ])
            else:
                best_lap = parseTime(car['bestlap'])
                cars.append(common_cols + [
                    (last_lap, 'pb' if last_lap == best_lap else ''),
                    (best_lap, ''),
                    car['pitstop']
                ])

            if best_lap > 0 and (category not in bestLapsByClass or bestLapsByClass[category][1] > best_lap):
                    bestLapsByClass[category] = (car['number'], best_lap)

        for car in cars:
            # Second pass to highlight sb/sb-new
            car_num = car[0]
            category = car[2]
            state = car[self.col_map[Stat.STATE]]
            s3 = car[self.col_map[Stat.S3]][0]

            # Best lap
            if category in bestLapsByClass and bestLapsByClass[category][0] == car_num:
                best_lap_time = bestLapsByClass[category][1]
                if self.is_qualifying_mode:
                    if car[self.col_map[Stat.DRIVER_1_BEST_LAP]][0] == best_lap_time:  # D1L1
                        car[self.col_map[Stat.DRIVER_1_BEST_LAP]] = (car[self.col_map[Stat.DRIVER_1_BEST_LAP]][0], 'sb')
                    elif car[self.col_map[Stat.DRIVER_2_BEST_LAP]][0] == best_lap_time:  # D2L1
                        car[self.col_map[Stat.DRIVER_2_BEST_LAP]] = (car[self.col_map[Stat.DRIVER_2_BEST_LAP]][0], 'sb')
                else:
                    car[self.col_map[Stat.BEST_LAP]] = (car[self.col_map[Stat.BEST_LAP]][0], 'sb')
                if car[self.col_map[Stat.LAST_LAP]][0] == best_lap_time and state == 'RUN' and s3 > 0:
                    car[self.col_map[Stat.LAST_LAP]] = (car[self.col_map[Stat.LAST_LAP]][0], 'sb-new')

            # Best sectors
            if category in bestSectorsByClass[1] and bestSectorsByClass[1][category][0] == car_num:
                car[self.col_map[Stat.BS1]] = (car[self.col_map[Stat.BS1]][0], 'sb')
                if car[self.col_map[Stat.S1]][0] == car[self.col_map[Stat.BS1]][0]:
                    car[self.col_map[Stat.S1]] = (car[self.col_map[Stat.S1]][0], 'sb')
            if category in bestSectorsByClass[2] and bestSectorsByClass[2][category][0] == car_num:
                car[self.col_map[Stat.BS2]] = (car[self.col_map[Stat.BS2]][0], 'sb')
                if car[self.col_map[Stat.S2]][0] == car[self.col_map[Stat.BS2]][0]:
                    car[self.col_map[Stat.S2]] = (car[self.col_map[Stat.S2]][0], 'sb')
            if category in bestSectorsByClass[3] and bestSectorsByClass[3][category][0] == car_num:
                car[self.col_map[Stat.BS3]] = (car[self.col_map[Stat.BS3]][0], 'sb')
                if car[self.col_map[Stat.S3]][0] == car[self.col_map[Stat.BS3]][0]:
                    car[self.col_map[Stat.S3]] = (car[self.col_map[Stat.S3]][0], 'sb')

        session['flagState'] = mapFlagState(self.params)

        session['timeElapsed'] = self.params['elapsed'] if 'elapsed' in self.params else None
        session['timeRemain'] = self.params['remaining'] if 'remaining' in self.params else None

        if 'trackTemp' in self.params:
            session['trackData'] = [
                "{}°C".format(self.params['trackTemp']),
                "{}°C".format(self.params['airTemp']),
                "{}%".format(self.params['humidity']),
                "{}kph".format(self.params['windSpeed']),
                "{}°".format(self.params['windDirection']),
                self.params['weather'].replace('_', ' ').title()
            ]

        return {
            "cars": cars,
            "session": session
        }
