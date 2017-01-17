# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import CarPitMessage, FastLapMessage, TimingMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from socketIO_client import SocketIO, BaseNamespace
from threading import Thread

import simplejson
import time


class RaceControlMessage(TimingMessage):
    def _consider(self, oldState, newState):
        if 'raceControlMessage' in newState and newState["raceControlMessage"] is not None:
            msg = newState["raceControlMessage"]
            return ["Race Control", msg, "raceControl"]


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
        self.raceControlMessage = None
        self.prevRaceControlMessage = None
        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelNamespaceFactory(feed, self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

    def session(self, data):
        self.sessionData.update(data)
        if 'participants' in data and not self.cars:
            for participant in data['participants']:
                self.cars.append([
                    participant['nr'],
                    '',
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
        for entry in data:
            car = self.cars[entry['id'] - 1]
            if 'st' in entry:
                car[1] = mapState(entry['st'])
            if 'part_id' in entry:
                participant = [p for p in self.sessionData['participants'] if p['id'] == entry['part_id']][0]
                car[0] = participant['nr']
                car[2] = u"{}, {}".format(participant['drivers'][0]['surname'].upper(), participant['drivers'][0]['name'])
                car[3] = [f for f in participant['fields'] if f['id'] == 'team'][0]['value']
                car[4] = [f for f in participant['fields'] if f['id'] == 'car'][0]['value']
            if 'laps' in entry:
                car[5] = entry['laps']
            if 'gap' in entry:
                car[6] = entry['gap']
            if 'prev' in entry:
                car[7] = entry['prev']
            if 's1' in entry:
                car[8] = (entry['s1'], mapModifier(entry['s1i']) if 's1i' in entry else '')
            if 's2' in entry:
                car[9] = (entry['s2'], mapModifier(entry['s2i']) if 's2i' in entry else '')
            if 's3' in entry:
                car[10] = (entry['s3'], mapModifier(entry['s3i']) if 's3i' in entry else '')
            if 'last' in entry:
                car[11] = (parseTime(entry['last']), mapModifier(entry['l_i']) if 'l_i' in entry else '')
            if 'best_time' in entry:
                car[12] = parseTime(entry['best_time'])
            if 'pits' in entry:
                car[13] = entry['pits']

    def st_update(self, data):
        self.st_refresh(data)

    def meteo(self, data):
        self.meteoData.update(data)

    def rc_message(self, data):
        self.raceControlMessage = data

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

    def getTrackDataSpec(self):
        return [
            "Air Temp",
            "Track Temp",
            "Humidity",
            "Pressure",
            "Wind Speed",
        ]

    def getPollInterval(self):
        return 1

    def getRaceState(self):
        session = {}
        session['trackData'] = [
            u"{:.3g}°C".format(float(self.meteoData["temp"])),
            u"{:.3g}°C".format(float(self.meteoData["track"])),
            "{}%".format(self.meteoData["hum"]),
            "{}mbar".format(self.meteoData["pres"]),
            "{:.2g}kph".format(float(self.meteoData["wind"])),
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

        session['raceControlMessage'] = self.raceControlMessage if self.raceControlMessage else None
        self.prevRaceControlMessage = self.raceControlMessage

        return {"cars": self.cars, "session": session}

    def getMessageGenerators(self):
        return super(Service, self).getMessageGenerators() + [
            CarPitMessage(lambda c: c[1], lambda c: "Pits", lambda c: c[2]),
            FastLapMessage(lambda c: c[11], lambda c: "Timing", lambda c: c[2]),
            RaceControlMessage()
        ]
