# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.analysis.lapchart import LapChart
from livetiming.analysis.laptimes import LaptimeChart
from livetiming.analysis.driver import StintLength
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.analysis.session import Session
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from socketIO_client import SocketIO, BaseNamespace
from threading import Thread

import argparse
import simplejson
import time


KNOWN_FEEDS = {
    'imsa': '910a7e3e-x15e-93a1-1007-r8c7xa149609',
    'elms': '41047e3e-c15e-53a1-9007-g1c3bc850710',
    'fiawec': 'a56c960a-3dff-48d1-a7bf-c076315ef22a',
    'formulae': '92200890-f282-11e3-ac10-0800200c9a66',
    'monza': '4d74d480-0ddf-11e6-a148-3e1d05defe78'
}


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


def mapFlag(rawFlag, yellowMeansCaution):
    flagMap = {
        'GF': FlagStatus.GREEN,
        'RF': FlagStatus.RED,
        'YF': FlagStatus.CAUTION if yellowMeansCaution else FlagStatus.YELLOW,
        'SF': FlagStatus.SC,
        'CH': FlagStatus.CHEQUERED
    }
    if rawFlag in flagMap:
        return flagMap[rawFlag].name.lower()
    return 'none'


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%S.%f")
        return ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def formatDriverName(driver):
    if driver['name'] != "":
        return u"{}, {}".format(driver['surname'].upper(), driver['name'])
    else:
        return driver['surname'].upper()


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", help="Feed ID")
    parser.add_argument("--caution", help="Understand 'yellow flag' to mean American-style full-course caution", action="store_true")
    parser.add_argument("--disable-class-column", help="Don't show class or PIC in timing", action="store_true")

    return parser.parse_args(args)


class Service(lt_service):
    attribution = ['Al Kamel Systems', 'http://www.alkamelsystems.com/']

    def __init__(self, args, extra_args, feed=None):
        lt_service.__init__(self, args, extra_args)

        self.extra_args = parse_extra_args(extra_args)
        self.feed = feed

        self.sessionData = {}
        self.meteoData = {}
        self.currentStanding = {}
        self.participants = {}
        self.messages = []
        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelNamespaceFactory(self.getFeedID(), self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

        self.hasTrackData = True
        self.prevRaceControlMessages = []

        self.flag_from_messages = None

    def getFeedID(self):
        if self.feed:
            feedID = self.feed
        elif self.extra_args.feed:
            feedID = self.extra_args.feed
        else:
            raise RuntimeError("No feed ID specified for Al Kamel! Cannot continue.")
        if feedID in KNOWN_FEEDS:
            return KNOWN_FEEDS[feedID]
        return feedID

    def session(self, data):

        newSession = (
            ("session_name" in data and "session_name" not in self.sessionData) or
            ("event_name" in data and "event_name" not in self.sessionData) or
            ("category" in data and "category" not in self.sessionData)
        )
        sessionChange = (
            ("session_name" in data and ("session_name" in self.sessionData and data["session_name"] != self.sessionData["session_name"])) or
            ("event_name" in data and ("event_name" in self.sessionData and data["event_name"] != self.sessionData["event_name"])) or
            ("category" in data and ("category" in self.sessionData and data["category"] != self.sessionData["category"]))
        )

        self.sessionData.update(data)

        if sessionChange:
            self.analyser.reset()  # Don't reset if this is the first session call since we started up, else we might accidentally delete data when we're restarted :()
        if sessionChange or newSession:
            self.publishManifest()  # since our description might have changed
            self.participants = {}
            self.currentStanding = {}

        def class_for(classID):
            possibles = [c for c in data["classes"] if c["id"] == classID]
            if len(possibles) > 0:
                return possibles[0]['n']
            return ""

        if 'participants' in data and not self.participants:
            for participant in data['participants']:
                self.participants[participant['id']] = participant

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
            car = self.currentStanding.get(entry['id'], {})
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
                if Stat.CLASS in cols:
                    car[cols[Stat.CLASS]] = class_for(participant['class_id'])
                car[cols[Stat.DRIVER]] = formatDriverName(participant['_active_driver'])
                car[cols[Stat.TEAM]] = [f for f in participant['fields'] if f['id'] == 'team'][0]['value']
                car[cols[Stat.CAR]] = [f for f in participant['fields'] if f['id'] == 'car'][0]['value']
            if 'dri_id' in entry:
                participant = [p for p in self.sessionData['participants'] if p['nr'] == car[cols[Stat.NUM]]][0]
                participant['_active_driver'] = [d for d in participant['drivers'] if d['id'] == int(entry['dri_id'])][0]
                car[cols[Stat.DRIVER]] = formatDriverName(participant['_active_driver'])
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
            self.currentStanding[entry['id']] = car

    def st_update(self, data):
        self.st_refresh(data)

    def meteo(self, data):
        if data:
            self.meteoData.update(data)
        else:
            self.hasTrackData = False
            self.publishManifest()

    def rc_message(self, data):
        flags_in_messages = []
        for msg in data:
            if msg['txt'] not in self.prevRaceControlMessages:
                # Duplicate messages can occur as the rc_message is resent after an st_refresh
                self.messages.append(msg['txt'])

            if msg['txt'] == "FULL COURSE YELLOW":
                flags_in_messages.append(FlagStatus.FCY)
            elif msg['txt'] == "SAFETY CAR":
                flags_in_messages.append(FlagStatus.SC)
            elif msg['txt'] == "CODE 60":
                flags_in_messages.append(FlagStatus.CODE_60)

        self.prevRaceControlMessages = map(lambda m: m['txt'], data)

        if flags_in_messages:
            self.flag_from_messages = max(flags_in_messages)
        else:
            self.flag_from_messages = None

    def getColumnSpec(self):
        base = [
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
        if not self.extra_args.disable_class_column:
            base.insert(2, Stat.CLASS)
            base.insert(3, Stat.POS_IN_CLASS)
        return base

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

    def getName(self):
        if "category" in self.sessionData:
            return self.sessionData["category"]
        return "Al Kamel feed"

    def getDefaultDescription(self):
        desc = ""

        if "event_name" in self.sessionData:
            desc = self.sessionData["event_name"].title()
            if "session_name" in self.sessionData:
                desc = u"{} - {}".format(desc, self.sessionData["session_name"].title())
        elif "session_name" in self.sessionData:
            desc = self.sessionData["session_name"].title()
        return desc

    def getRaceState(self):
        session = {}
        if self.hasTrackData:
            session['trackData'] = [
                u"{:.3g}°C".format(float(self.meteoData["temp"])) if "temp" in self.meteoData else "",
                u"{:.3g}°C".format(float(self.meteoData["track"])) if "track" in self.meteoData else "",
                "{}%".format(self.meteoData["hum"]) if "hum" in self.meteoData else "",
                "{} mbar".format(self.meteoData["pres"]) if "pres" in self.meteoData else "",
                "{:.2g} kph".format(float(self.meteoData["wind"])) if "wind" in self.meteoData else "",
            ]

        if self.flag_from_messages:
            session['flagState'] = self.flag_from_messages.name.lower()
        else:
            session['flagState'] = mapFlag(self.sessionData.get('flag', "none"), self.extra_args.caution)

        if 'remaining' in self.sessionData and self.sessionData['remaining']:
            current_remaining = self.sessionData['remaining']
            if current_remaining['running']:
                session['timeElapsed'] = time.time() - current_remaining['startTime'] - current_remaining['deadTime']
            else:
                session['timeElapsed'] = current_remaining['stopTime'] - current_remaining['startTime'] - current_remaining['deadTime']

            if current_remaining['finaltype'] == 1:
                session['timeRemain'] = current_remaining['finalTime'] - session['timeElapsed']
            elif current_remaining['finaltype'] == 2:
                session['lapsRemain'] = max(0, current_remaining['lapsTotal'] - current_remaining['lapsElapsed'])

        colspec = self.getColumnSpec()
        cars = map(lambda c: c.values(), self.currentStanding.values())
        classes_count = {}
        for car in cars:

            if Stat.CLASS in colspec:
                my_class = car[colspec.index(Stat.CLASS)]
                classes_count[my_class] = classes_count.get(my_class, 0) + 1

                car.insert(3, classes_count[my_class])
            best = car[colspec.index(Stat.BEST_LAP)]
            last = car[colspec.index(Stat.LAST_LAP)]
            s3 = car[colspec.index(Stat.S3)]
            if last[1] == "sb" and best == last[0] and s3[0] != "":
                car[colspec.index(Stat.LAST_LAP)] = (last[0], "sb-new")
            elif last[1] == "sb-new" and s3[0] == "":
                car[colspec.index(Stat.LAST_LAP)] = (last[0], "sb")
            elif last[0] == best:
                car[colspec.index(Stat.LAST_LAP)] = (last[0], 'pb')

        return {"cars": cars, "session": session}

    def getExtraMessageGenerators(self):
        return [
            RaceControlMessage(self.messages)
        ]

    def getAnalysisModules(self):
        return [
            Session,
            LapChart,
            LaptimeChart,
            StintLength,
            EnduranceStopAnalysis
        ]
