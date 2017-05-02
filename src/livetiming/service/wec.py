# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.analysis.driver import StintLength
from livetiming.analysis.laptimes import LaptimeChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service, JSONFetcher
from twisted.logger import Logger

import re
import simplejson
import time
from __builtin__ import True
from simplejson.scanner import JSONDecodeError
from socketIO_client import BaseNamespace, SocketIO
from livetiming.service.alkamel import KNOWN_FEEDS
from threading import Thread
from livetiming.messages import RaceControlMessage


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
        'Out': 'OUT'
    }
    if rawState in stateMap:
        return stateMap[rawState]
    Logger().warn("Unknown car state {}".format(rawState))
    return rawState


def parseTime(formattedTime):
    if formattedTime == "":
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


def AlkamelRCOnlyNamespaceFactory(handler):
    class AlkamelNamespace(BaseNamespace):
        def on_connect(self, *args):
            self.emit('st', {"feed": KNOWN_FEEDS['fiawec'], "ver": "1.0"})

        def on_rc_message(self, data):
            handler.rc_message(simplejson.loads(data.encode('iso-8859-1')))

    return AlkamelNamespace


class Service(lt_service):
    log = Logger()

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)
        self.params = {}
        self.entries = []
        self.latest_seen_timestamp = None

        self.messages = []
        self.prevRaceControlMessages = []

        self.description = "World Endurance Championship"

        def data_url():
            return "http://www.fiawec.com/ecm/live/WEC/data.json?_={}".format(int(1000 * time.time()))

        fetcher = JSONFetcher(data_url, self._handleData, 10)
        fetcher.start()

        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelRCOnlyNamespaceFactory(self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

    def getName(self):
        return "WEC"

    def getDefaultDescription(self):
        return self.description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
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
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.SPEED,
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

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]

    def getAnalysisModules(self):
        return [
            LaptimeChart,
            EnduranceStopAnalysis,
            StintLength
        ]

    def rc_message(self, data):
        for msg in data:
            if msg['txt'] not in self.prevRaceControlMessages:
                # Duplicate messages can occur as the rc_message is resent after an st_refresh
                self.messages.append(msg['txt'])

        self.prevRaceControlMessages = map(lambda m: m['txt'], data)

    def _data_is_newer(self, params):
        if self.latest_seen_timestamp is None:
            return True
        if "timestamp" not in params:
            return True
        return params["timestamp"] > self.latest_seen_timestamp

    def _handleData(self, data):
        if "params" in data:
            try:
                new_params = simplejson.loads(data["params"])
                if self._data_is_newer(new_params):
                    self.params = new_params
                    if 'eventName' in self.params and self.params['eventName'] != self.description:
                        self.description = self.params['eventName']
                        self.publishManifest()

                    self.latest_seen_timestamp = self.params.get("timestamp", None)

                if "entries" in data:
                    try:
                        self.entries = simplejson.loads(data["entries"])
                    except JSONDecodeError:
                        self.sentry.captureException()
                        self.log.failure("Failed to parse WEC entry data {entries}: {log_failure}", entries=data['entries'])

            except JSONDecodeError:
                self.sentry.captureException()
                self.log.failure("Failed to parse WEC subdata {params}: {log_failure}", params=data['params'])
            self._updateAndPublishRaceState()

    def getRaceState(self):
        cars = []
        session = {}

        bestLapsByClass = {}
        bestSectorsByClass = {1: {}, 2: {}, 3: {}}

        for car in self.entries:
            category = car['category']
            last_lap = parseTime(car['lastlap'])
            best_lap = parseTime(car['bestlap'])

            s1 = parseTime(car['currentSector1'])
            bs1 = parseTime(car['bestSector1'])
            s2 = parseTime(car['currentSector2'])
            bs2 = parseTime(car['bestSector2'])
            s3 = parseTime(car['currentSector3'])
            bs3 = parseTime(car['bestSector3'])

            if car['bestlap'] != "" and (category not in bestLapsByClass or bestLapsByClass[category][1] > best_lap):
                bestLapsByClass[category] = (car['number'], best_lap)

            if bs1 > 0 and (category not in bestSectorsByClass[1] or bestSectorsByClass[1][category][1] > bs1):
                bestSectorsByClass[1][category] = (car['number'], bs1)
            if bs2 > 0 and (category not in bestSectorsByClass[2] or bestSectorsByClass[2][category][1] > bs2):
                bestSectorsByClass[2][category] = (car['number'], bs2)
            if bs3 > 0 and (category not in bestSectorsByClass[3] or bestSectorsByClass[3][category][1] > bs3):
                bestSectorsByClass[3][category] = (car['number'], bs3)

            cars.append([
                car['number'],
                mapCarState(car['state']),
                category,
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
                (bs3, 'old' if s3 != bs3 else ''),
                (last_lap, 'pb' if last_lap == best_lap else ''),
                (best_lap, ''),
                car['speed'],
                car['pitstop']
            ])

        for car in cars:
            # Second pass to highlight sb/sb-new
            car_num = car[0]
            category = car[2]
            if category in bestLapsByClass and bestLapsByClass[category][0] == car_num:
                car[17] = (car[17][0], 'sb')
                if car[16][0] == car[17][0]:
                    car[16] = (car[16][0], 'sb-new')
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
        session['timeRemain'] = self.params['remaining'] if 'remaining' in self.params else None

        if 'trackTemp' in self.params:
            session['trackData'] = [
                u"{}°C".format(self.params['trackTemp']),
                u"{}°C".format(self.params['airTemp']),
                "{}%".format(self.params['humidity']),
                "{}kph".format(self.params['windSpeed']),
                u"{}°".format(self.params['windDirection']),
                self.params['weather'].title()
            ]

        return {
            "cars": cars,
            "session": session
        }
