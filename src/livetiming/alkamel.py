# -*- coding: utf-8 -*-
from livetiming.service import Service as lt_service
from socketIO_client import SocketIO, BaseNamespace
from threading import Thread

import simplejson
from livetiming.racing import FlagStatus


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
            handler.st_refresh(simplejson.loads(data))

        def on_st_update(self, data):
            handler.st_update(simplejson.loads(data))

        def on_meteo(self, data):
            handler.meteo(simplejson.loads(data))

        def on_session(self, data):
            handler.session(simplejson.loads(data))

        def on_rc_message(self, data):
            handler.rc_message(simplejson.loads(data))

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


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        self.sessionData = {}
        self.meteoData = {}
        self.cars = []
        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelNamespaceFactory("92200890-f282-11e3-ac10-0800200c9a66", self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

    def session(self, data):
        self.sessionData = data
        self.cars = []
        if 'participants' in data:
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
                car[11] = (entry['last'], mapModifier(entry['l_i']) if 'l_i' in entry else '')
            if 'best_time' in entry:
                car[12] = entry['best_time']
            if 'pits' in entry:
                car[13] = entry['pits']

    def st_update(self, data):
        self.st_refresh(data)

    def meteo(self, data):
        self.meteoData.update(data)

    def rc_message(self, data):
        print "Race control:"
        print data

    def getColumnSpec(self):
        return [
            ("Num", "text"),
            ("State", "text"),
            ("Driver", "text"),
            ("Team", "text"),
            ("Car", "text"),
            ("Laps", "numeric"),
            ("Gap", "time"),
            ("Int", "time"),
            ("S1", "time"),
            ("S2", "time"),
            ("S3", "time"),
            ("Last", "time"),
            ("Best", "time"),
            ("Pits", "numeric")
        ]

    def getTrackDataSpec(self):
        return [
            "Air Temp",
            "Track Temp",
            "Humidity",
            "Pressure",
            "Wind Speed",
        ]

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

        return {"cars": self.cars, "session": session}
