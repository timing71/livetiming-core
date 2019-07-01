# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import RaceControlMessage, PerCarMessage
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service
from requests.sessions import Session
from signalr import Connection
from threading import Thread
from kitchen.text.converters import to_bytes, to_unicode

import argparse
import re


from livetiming.signalr_patches import patch_signalr
patch_signalr()


class TSLClient(Thread):

    def __init__(self, handler, host="livetiming.tsl-timing.com", sessionID="WebDemo", sprint=False):
        Thread.__init__(self)
        self.handler = handler
        self.log = handler.log
        self.host = host
        self.sessionID = sessionID
        self.sprint = sprint
        self.daemon = True

    def run(self):
        with Session() as session:
            connection = Connection("http://{}/signalr/".format(self.host), session)
            hub = connection.register_hub('livetiming')

            def print_error(error):
                print(('error: ', error))

            def delegate(method, data):
                handler_method = "on_{}".format(method.lower())
                if hasattr(self.handler, handler_method) and callable(getattr(self.handler, handler_method)):
                    self.log.debug("Received {method}: {data}", method=method, data=data)
                    getattr(self.handler, handler_method)(data)
                else:
                    self.log.info("Unhandled message {method}: {data}", method=handler_method, data=data)

            def handle(**kwargs):
                if 'M' in kwargs:
                    for msg in kwargs['M']:
                        delegate(msg['M'], msg['A'])

            connection.error += print_error
            connection.received += handle

            with connection:
                hub.server.invoke('RegisterConnectionId', self.sessionID, True, True, True)
                hub.server.invoke_then('GetClassification', self.sessionID)(lambda d: delegate('classification', d))
                hub.server.invoke_then('GetSessionData', self.sessionID)(lambda d: delegate('session', d))
                hub.server.invoke_then('GetIntermediatesTimes', self.sessionID)(lambda d: delegate('sectortimes', d))

                if self.sprint:
                    hub.server.invoke_then('GetSprintCompetitors', self.sessionID)(lambda d: delegate('updatesprintcompetitor', d))
                    hub.server.invoke_then('GetSprintDrivers', self.sessionID)(lambda d: delegate('updatesprintdriver', d))
                    hub.server.invoke_then('GetSprintRuns', self.sessionID)(lambda d: delegate('updatesprintrun', d))

                connection.wait(None)


class SprintStateMessage(PerCarMessage):
    def _consider(self, oldCar, newCar):
        oldState = self.getValue(oldCar, Stat.STATE, "")
        newState = self.getValue(newCar, Stat.STATE, "")
        clazz = self.getValue(newCar, Stat.CLASS, "")
        carNum = self.getValue(newCar, Stat.NUM)
        driver = self.getValue(newCar, Stat.DRIVER)

        if newState != oldState:
            if newState == "RUN":
                return [clazz, "#{} ({}) has started a run".format(carNum, driver), "green"]


def mapState(state, inPit):
    if inPit:
        return "PIT"
    if state == "Running":
        return "RUN"
    if state == "Finished":
        return "FIN"
    if state == "Missing":
        return "?"
    if state == 'NotStarted':
        return 'N/S'
    return state


def parseTime(formattedTime):
    if formattedTime is None:
        return None
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%S.%f")
            return ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
            return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def mapSessionState(state):
    mapping = {
        'Green': FlagStatus.GREEN,
        'Red': FlagStatus.RED,
        'Yellow': FlagStatus.SC,
        'FCY': FlagStatus.FCY,
        'Finished': FlagStatus.CHEQUERED,
        'Complete': FlagStatus.CHEQUERED,
        'Pending': FlagStatus.NONE,
        'Active': FlagStatus.NONE
    }
    if state in mapping:
        return mapping[state]
    print("Unknown flag state: {}".format(state))
    return FlagStatus.NONE


def format_driver_name(driver):
    if 'FirstName' in driver and 'LastName' in driver:
        return "{} {}".format(driver['FirstName'], driver['LastName'].upper())
    return ''


def parseExtraArgs(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="TSL session ID", required=True)
    parser.add_argument("--host", help="TSL host")
    parser.add_argument("--sprint", help="TSL sprint mode", action="store_true")

    a, _ = parser.parse_known_args(extra_args)
    return a


RACE_CONTROL_PREFIX_REGEX = re.compile("^[0-9]{2}:[0-9]{2}:[0-9]{2}: (?P<text>.*)")


SECTOR_STATS = [
    Stat.S1,
    Stat.S2,
    Stat.S3,
    Stat.S4,
    Stat.S5,
]


class Service(lt_service):
    attribution = ['TSL Timing', 'https://www.tsl-timing.com/']

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)

        my_args = parseExtraArgs(extra_args)
        client = TSLClient(self, host=self.getHost(my_args.host), sessionID=my_args.session, sprint=my_args.sprint)
        client.start()

        self.sprint = my_args.sprint
        self.name = "TSL Timing"
        self.description = ""

        self.cars = {}
        self.sectorTimes = {}
        self.trackSectors = {}
        self.bestSectorTimes = {}
        self.bestLap = None
        self.sprint_drivers = {}
        self.sprint_competitors = {}
        self.sprint_runs = {}
        self.messages = []

        self.flag = FlagStatus.NONE
        self.timeRemaining = -1
        self.timeReference = datetime.utcnow()
        self.lapsRemaining = None
        self.startTime = None
        self.clockRunning = False
        self.sessionID = None

        self.weather = {
            'tracktemp': None,
            'trackstate': None,
            'airtemp': None,
            'conditions': None,
            'airpressure': None,
            'windspeed': None,
            'winddir': None,
            'humidity': None
        }

    def getHost(self, host=None):
        if not host:
            return "livetiming.tsl-timing.com"
        return host

    def getColumnSpec(self):
        if self.sprint:
            return [
                Stat.NUM,
                Stat.CLASS,
                Stat.STATE,
                Stat.DRIVER,
                Stat.CAR,
                Stat.LAPS,
                Stat.GAP,
                Stat.INT,
                Stat.LAST_LAP,
                Stat.BEST_LAP
            ]
        return [
            Stat.NUM,
            Stat.CLASS,
            Stat.STATE,
            Stat.DRIVER,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT
        ] + SECTOR_STATS[0:len(self.trackSectors)] + [
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getName(self):
        return self.name

    def getDefaultDescription(self):
        return self.description

    def getPollInterval(self):
        return 1

    def getTrackDataSpec(self):
        return [
            "Track temp",
            "Track state",
            "Air temp",
            "Conditions",
            "Air pressure",
            "Wind speed",
            "Direction",
            "Humidity"
        ]

    def getExtraMessageGenerators(self):
        mgs = [
            RaceControlMessage(self.messages),
        ]

        if self.sprint:
            mgs.append(SprintStateMessage(self.getColumnSpec()))

        return mgs

    def sectorTimeFor(self, car, sector):
        if car['ID'] not in self.sectorTimes:
            return ("", "")
        stuple = self.sectorTimes[car["ID"]][sector]
        if stuple[0] == self.bestSectorTimes.get(sector, -1) / 1e6:
            return (stuple[0], 'sb')
        return stuple

    def getCars(self):
        cars = []

        for car in sorted(list(self.cars.values()), key=lambda c: c['Pos']):
            car_state = "OUT" if 'out_lap' in car else mapState(car['Status'], car['InPits'])
            bestTime = parseTime(car['CurrentSessionBest'])
            bestTimeFlag = 'sb' if self.bestLap and self.bestLap[0] == car['ID'] else ''

            lastTime = parseTime(car['LastLapTime'])

            sector_times = [self.sectorTimeFor(car, i) for i in range(len(self.trackSectors))]

            s1_time = sector_times[0]
            final_sector_time = sector_times[-1]

            if lastTime == bestTime and bestTimeFlag == 'sb':
                lastTimeFlag = 'sb-new' if s1_time[0] != '' and final_sector_time[0] != '' and car_state != 'PIT' else 'sb'
            else:
                lastTimeFlag = 'pb' if car['PersonalBestTime'] else ''

            display_class = car['SubClass'] or car['PrimaryClass'] or ''

            cars.append([
                car['StartNumber'],
                display_class,
                car_state,
                to_unicode(to_bytes(car['Name'])) or format_driver_name(self.sprint_drivers.get(car['ID'], '')),
                car['Vehicle'],
                car['Laps'],
                car['Gap'],
                car['Diff'],
            ] + sector_times + [
                (lastTime if lastTime > 0 else '', lastTimeFlag),
                (bestTime if bestTime > 0 else "", bestTimeFlag),
                car.get('PitStops', '')
            ])

        return cars

    def getSprintCars(self):
        cars = []
        for car in sorted(list(self.sprint_competitors.values()), key=lambda c: c['Position'] if c['Position'] > 0 else 9999):
            runs = self.sprint_runs.get(car['ID'], [])
            classification = self.cars.get(car['ID'], {})
            isOnRun = False

            if len(runs) > 0:
                driver = format_driver_name(self.sprint_drivers.get(runs[-1]['DriverID'], '')).strip()
                lastRun = runs[-1]
                if not lastRun['IsComplete']:
                    isOnRun = True
                lastTime = None
                if "Times" in lastRun and len(lastRun["Times"]) > 0:
                    if "LapTime" in lastRun["Times"][0] and lastRun['Times'][0]['LapTime'] > 0:
                        lastTime = lastRun['Times'][0]['LapTime']
            else:
                driver = ''
                lastRun = None
                lastTime = None

            cars.append([
                car['No'],
                car['Class'],
                "RUN" if isOnRun else mapState(classification.get('Status', ''), classification.get('InPits', False)),
                driver,
                car['Vehicle'],
                len(runs),
                classification.get('Gap', ''),
                classification.get('Diff', ''),
                (float(lastTime), "") if lastTime and float(lastTime) > 0 else ("", ""),
                (parseTime(classification.get('CurrentSessionBest', "")), "")
            ])

        return cars

    def getRaceState(self):
        now = datetime.utcnow()

        if self.sprint:
            cars = self.getSprintCars()
        else:
            cars = self.getCars()

        return {
            "cars": cars,
            "session": {
                "flagState": self.flag.name.lower(),
                "timeElapsed": (now - self.startTime).total_seconds() if self.startTime else 0,
                "timeRemain": max(self.timeRemaining - (now - self.timeReference).total_seconds(), 0) if self.clockRunning else self.timeRemaining,
                "trackData": [
                    "{}°C".format(self.weather['tracktemp'] or '-'),
                    self.weather['trackstate'],
                    "{}°C".format(self.weather['airtemp'] or '-'),
                    self.weather['conditions'],
                    "{}mb".format(self.weather['airpressure'] or '-'),
                    "{}mph".format(self.weather['windspeed'] or '-'),
                    "{}°".format(self.weather['winddir'] or '-'),
                    "{}%".format(self.weather['humidity'] or '-')
                ]
            }
        }

    def on_session(self, data):
        if "Series" in data:
            self.name = data["Series"]
        if "TrackDisplayName" in data or "Name" in data:
            if data["TrackDisplayName"] and data["Name"]:
                self.description = "{} - {}".format(data["TrackDisplayName"], data["Name"].title())
            elif data["TrackDisplayName"]:
                self.description = data["TrackDisplayName"]
            elif data["Name"]:
                self.description = data["Name"].title()
        if "State" in data:
            self.flag = mapSessionState(data['State'])
        if "TrackConditions" in data:
            self.weather['trackstate'] = data['TrackConditions']
        if 'WeatherConditions' in data:
            self.weather['conditions'] = data['WeatherConditions']
        if "LapsRemaining" in data:
            self.lapsRemaining = data["LapsRemaining"]
        if "TrackSectors" in data:
            for sector in data["TrackSectors"]:
                if sector["Name"][0] == "S" and len(sector["Name"]) == 2:
                    self.trackSectors[sector['ID']] = int(sector["Name"][1]) - 1
                    self.bestSectorTimes[self.trackSectors[sector['ID']]] = sector["BestTime"]
        if "ActualStart" in data and data["ActualStart"] and "UTCOffset" in data:
            self.startTime = datetime.utcfromtimestamp((data["ActualStart"] - data["UTCOffset"]) / 1e6)
        if 'FastLapCompetitorID' in data and 'FastLapTime' in data:
            self.bestLap = (data['FastLapCompetitorID'], parseTime(data['FastLapTime']))

        if self.sessionID != data.get('ID'):
            if self.sessionID:
                self.cars.clear()
            self.sessionID = data['ID']
        self.publishManifest()

    def on_sdbroadcast(self, data):
        self.on_session(data[0])

    def on_updatesprintsession(self, data):
        pass

    def on_classification(self, data):
        for car in data:
            self.cars[car['ID']] = car

    def on_settimeremaining(self, data):
        self.timeRemaining = (60 * (60 * int(data[0]['d'][0]) + int(data[0]['d'][1]))) + int(data[0]['d'][2])
        self.timeReference = datetime.utcnow()
        self.clockRunning = data[0]["r"]

    def on_updateweather(self, datas):
        data = datas[0]
        self.weather.update({
            'tracktemp': data['TrackTemp'],
            'airtemp': data['AirTemp'],
            'airpressure': data['Pressure'],
            'windspeed': data['WindSpeed'],
            'winddir': data['WindDirection'],
            'humidity': data['Humidity']
        })

    def on_updateresult(self, data):
        self.on_classification(data)

    def on_updatesession(self, data):
        self.on_session(data[0])

    def on_addintermediate(self, data):
        self.on_sectortimes(data)

    def on_controlbroadcast(self, data):
        for msg in data:
            if msg['Message'] != "":
                text = msg['Message']
                has_time_prefix = RACE_CONTROL_PREFIX_REGEX.match(text)
                if has_time_prefix:
                    self.messages.append(has_time_prefix.group('text'))
                else:
                    self.messages.append(text)

    def on_sectortimes(self, data):
        for d in data:
            cid = d["CompetitorID"]
            if cid not in self.sectorTimes:
                self.sectorTimes[cid] = [("", ""), ("", ""), ("", ""), ("", ""), ("", "")]
            sector = self.trackSectors.get(d["Id"], -1)
            if sector >= 0 and d["Time"] > 0:
                self.sectorTimes[cid][sector] = (d["Time"] / 1e6, "pb" if d["Time"] == d["BestTime"] else "")
                if sector == 0:
                    self.sectorTimes[cid][1] = (self.sectorTimes[cid][1][0], self.sectorTimes[cid][1][1] or 'old')
                    self.sectorTimes[cid][2] = (self.sectorTimes[cid][2][0], self.sectorTimes[cid][2][1] or 'old')

    def on_updatesector(self, data):
        for s in data:
            sector = self.trackSectors.get(s["ID"], -1)
            if sector >= 0:
                self.bestSectorTimes[sector] = s["BestTime"]

    def on_competitorpitout(self, data):
        for c in data:
            cid = c['CompetitorID']
            if cid in self.cars:
                self.cars[cid]['out_lap'] = True
            else:
                print("Pit out for unknown competitor: {}".format(c))

    def on_updatesprintdriver(self, data):
        for driver in data:
            self.sprint_drivers[driver['ID']] = driver

    def on_updatesprintrun(self, data):
        for run in data:
            if run['TeamID'] not in self.sprint_runs:
                self.sprint_runs[run['TeamID']] = []
            if len(self.sprint_runs[run['TeamID']]) > 0:
                if self.sprint_runs[run['TeamID']][-1]['RunNo'] == run['RunNo']:
                    self.sprint_runs[run['TeamID']].pop()
            self.sprint_runs[run['TeamID']].append(run)

    def on_updatesprintcompetitor(self, data):
        for comp in data:
            self.sprint_competitors[comp['ID']] = comp

    def on_mapanimate(self, _):
        pass

    def on_removeanimation(self, _):
        pass

    def on_removecompetitor(self, competitors):
        # I'm unconvinced by:
        # for compID in competitors:
        #     if compID in self.cars:
        #         del self.cars[compID]
        pass

    # We don't use the class data so we can ignore these.
    def on_updateclass(self, _):
        pass

    def on_removeclass(self, _):
        pass
