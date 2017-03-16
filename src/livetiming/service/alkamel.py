# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from socketIO_client import SocketIO, BaseNamespace
from threading import Thread

import simplejson
import time
from livetiming.analysis.laptimes import LaptimeAnalysis
from livetiming.analysis.driver import StintLength
from livetiming.analysis.pits import PitStopAnalysis


def AlkamelNamespaceFactory(feedID, handler):
    class AlkamelNamespace(BaseNamespace):
        def on_connect(self, *args):
            self.emit('st', {"feed": feedID, "ver": "1.0"})

        def on_stOK(self, data):
            features = simplejson.loads(data)["features"]
            if features['timing'] == '1':
                self.emit('subscribe', 't')  # Timing
            if features['meteo'] == '1':
                self.emit('subscribe', 'm')  # Weather
            else:
                handler.meteo(False)

        def on_st_refresh(self, data):
            handler.st_refresh(simplejson.loads(data.encode('iso-8859-1')))

        def on_st_update(self, data):
            handler.st_update(simplejson.loads(data.encode('iso-8859-1')))

        def on_meteo(self, data):
            handler.meteo(simplejson.loads(data.encode('iso-8859-1')))

        def on_session(self, data):
            handler.session(simplejson.loads(data.encode('iso-8859-1')))

        def on_rc_message(self, data):
            handler.rc_message(simplejson.loads(data.encode('iso-8859-1')))

    return AlkamelNamespace


def mapState(rawState):
    stateMap = {
        'i': 'PIT',
        'o': 'OUT',
        'r': 'RUN',
        's': 'RET',
        'c': 'FIN'
    }
    if rawState in stateMap:
        return stateMap[rawState]
    return rawState


def mapModifier(rawMod):
    modMap = {
        's': 'sb',
        'p': 'pb',
        'n': ''
    }
    if rawMod in modMap:
        return modMap[rawMod]
    return rawMod


def mapFlag(rawFlag):
    flagMap = {
        'GF': FlagStatus.GREEN,
        'RF': FlagStatus.RED,
        'YF': FlagStatus.YELLOW,
        'SF': FlagStatus.WHITE,
        'CH': FlagStatus.CHEQUERED
    }
    if rawFlag in flagMap:
        return flagMap[rawFlag].name.lower()
    return 'none'


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
        return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


class Service(lt_service):
    def __init__(self, config, feed):
        lt_service.__init__(self, config)
        self.sessionData = {}
        self.meteoData = {}
        self.cars = []
        self.messages = []
        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelNamespaceFactory(feed, self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

        self.hasTrackData = True
        self.prevRaceControlMessage = None

    def session(self, data):

        sessionChange = (
            ("session_name" in data and ("session_name" not in self.sessionData or data["session_name"] != self.sessionData["session_name"])) or
            ("category" in data and ("category" not in self.sessionData or data["category"] != self.sessionData["category"]))
        )

        self.sessionData.update(data)

        if sessionChange:
            self.publishManifest()  # since our description might have changed
            self.analyser.reset()
            self.cars = []

        def class_for(classID):
            possibles = [c for c in data["classes"] if c["id"] == classID]
            if len(possibles) > 0:
                return possibles[0]['n']
            return ""

        if 'participants' in data and not self.cars:
            for participant in data['participants']:
                self.cars.append([
                    participant['nr'],
                    '',
                    class_for(participant['class_id']),
                    u"{}, {}".format(participant['drivers'][0]['surname'].upper(), participant['drivers'][0]['name']),
                    [f for f in participant['fields'] if f['id'] == 'team'][0]['value'],
                    [f for f in participant['fields'] if f['id'] == 'car'][0]['value'],
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    ''
                ])

    def st_refresh(self, data):
        cols = {}

        def class_for(classID):
            possibles = [c for c in self.sessionData["classes"] if c["id"] == classID]
            if len(possibles) > 0:
                return possibles[0]['n']
            return ""

        for idx, col in enumerate(self.getColumnSpec()):
            cols[col] = idx
        for entry in data:
            car = self.cars[entry['id'] - 1]
            if 'st' in entry:
                car[cols[Stat.STATE]] = mapState(entry['st'])
            if 'part_id' in entry:
                participant = [p for p in self.sessionData['participants'] if p['id'] == entry['part_id']][0]
                if 'dri_id' in entry:
                    participant['_active_driver'] = [d for d in participant['drivers'] if d['id'] == int(entry['dri_id'])][0]
                if '_active_driver' not in participant:
                    self.log.warn("No active driver for {}, using first listed driver".format(participant['nr']))
                    participant['_active_driver'] = participant['drivers'][0]
                car[cols[Stat.NUM]] = participant['nr']
                car[cols[Stat.CLASS]] = class_for(participant['class_id'])
                car[cols[Stat.DRIVER]] = u"{}, {}".format(participant['_active_driver']['surname'].upper(), participant['_active_driver']['name'])
                car[cols[Stat.TEAM]] = [f for f in participant['fields'] if f['id'] == 'team'][0]['value']
                car[cols[Stat.CAR]] = [f for f in participant['fields'] if f['id'] == 'car'][0]['value']
            if 'dri_id' in entry:
                participant = [p for p in self.sessionData['participants'] if p['nr'] == car[cols[Stat.NUM]]][0]
                participant['_active_driver'] = [d for d in participant['drivers'] if d['id'] == int(entry['dri_id'])][0]
                car[cols[Stat.DRIVER]] = u"{}, {}".format(participant['_active_driver']['surname'].upper(), participant['_active_driver']['name'])
            if 'laps' in entry:
                car[cols[Stat.LAPS]] = entry['laps']
            if 'gap' in entry:
                car[cols[Stat.GAP]] = entry['gap']
            if 'prev' in entry:
                car[cols[Stat.INT]] = entry['prev']
            if 's1' in entry:
                car[cols[Stat.S1]] = (entry['s1'], mapModifier(entry['s1i']) if 's1i' in entry else '')
            elif 's1i' in entry:
                car[cols[Stat.S1]] = (car[cols[Stat.S1]][0], mapModifier(entry['s1i']))
            if 's2' in entry:
                car[cols[Stat.S2]] = (entry['s2'], mapModifier(entry['s2i']) if 's2i' in entry else '')
            elif 's2i' in entry:
                car[cols[Stat.S2]] = (car[cols[Stat.S2]][0], mapModifier(entry['s2i']))
            if 's3' in entry:
                car[cols[Stat.S3]] = (entry['s3'], mapModifier(entry['s3i']) if 's3i' in entry else '')
            elif 's3i' in entry:
                car[cols[Stat.S3]] = (car[cols[Stat.S3]][0], mapModifier(entry['s3i']))
            if 'last' in entry:
                car[cols[Stat.LAST_LAP]] = (parseTime(entry['last']), mapModifier(entry['l_i']) if 'l_i' in entry else '')
            elif 'l_i' in entry:
                car[cols[Stat.LAST_LAP]] = (car[cols[Stat.LAST_LAP]][0], mapModifier(entry['l_i']))
            if 'best_time' in entry:
                car[cols[Stat.BEST_LAP]] = parseTime(entry['best_time'])
            if 'pits' in entry:
                car[cols[Stat.PITS]] = entry['pits']

    def st_update(self, data):
        self.st_refresh(data)

    def meteo(self, data):
        if data:
            self.meteoData.update(data)
        else:
            self.hasTrackData = False
            self.publishManifest()

    def rc_message(self, data):
        for msg in data:
            if msg['txt'] != self.prevRaceControlMessage:
                # Duplicate messages can occur as the rc_message is resent after an st_refresh
                self.messages.append(msg['txt'])
                self.prevRaceControlMessage = msg['txt']

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
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

    def getTrackDataSpec(self):
        if self.hasTrackData:
            return [
                "Air Temp",
                "Track Temp",
                "Humidity",
                "Pressure",
                "Wind Speed",
            ]
        return []

    def getPollInterval(self):
        return 1

    def getDefaultDescription(self):
        desc = ""

        if "category" in self.sessionData:
            desc = self.sessionData["category"]
        if "session_name" in self.sessionData:
            desc = "{} - {}".format(desc, self.sessionData["session_name"])
        return desc

    def getRaceState(self):
        session = {}
        if self.hasTrackData:
            session['trackData'] = [
                u"{:.3g}°C".format(float(self.meteoData["temp"])) if "temp" in self.meteoData else "",
                u"{:.3g}°C".format(float(self.meteoData["track"])) if "track" in self.meteoData else "",
                "{}%".format(self.meteoData["hum"]) if "hum" in self.meteoData else "",
                "{}mbar".format(self.meteoData["pres"]) if "pres" in self.meteoData else "",
                "{:.2g}kph".format(float(self.meteoData["wind"])) if "wind" in self.meteoData else "",
            ]

        session['flagState'] = mapFlag(self.sessionData['flag'])

        if self.sessionData['remaining']:
            current_remaining = self.sessionData['remaining']
            if current_remaining['running']:
                session['timeElapsed'] = time.time() - current_remaining['startTime'] - current_remaining['deadTime']
            else:
                session['timeElapsed'] = current_remaining['stopTime'] - current_remaining['startTime'] - current_remaining['deadTime']

            if current_remaining['finaltype'] == 1:
                session['timeRemain'] = current_remaining['finalTime'] - session['timeElapsed']
            elif current_remaining['finaltype'] == 2:
                session['lapsRemain'] = max(0, current_remaining['lapsTotal'] - current_remaining['lapsElapsed'])

        return {"cars": self.cars, "session": session}

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]

    def getAnalysisModules(self):
        return [
            LaptimeAnalysis,
            StintLength,
            PitStopAnalysis
        ]
