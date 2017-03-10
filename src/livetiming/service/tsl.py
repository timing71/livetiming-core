# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service
from requests.sessions import Session
from signalr import Connection
from signalr.hubs._hub import HubServer
from signalr.events._events import EventHook
from threading import Thread


###################################
# BEGIN patches to signalr-client #
###################################
def invoke_then(self, method, *data):
    send_counter = self._HubServer__connection.increment_send_counter()

    def then(func):
        def onServerResponse(**kwargs):
            if 'I' in kwargs and int(kwargs['I']) == send_counter:
                    if 'R' in kwargs:
                        func(kwargs['R'])
                    return False
        self._HubServer__connection.received += onServerResponse

        self._HubServer__connection.send({
            'H': self.name,
            'M': method,
            'A': data,
            'I': send_counter
        })
    return then

HubServer.invoke_then = invoke_then


def fire(self, *args, **kwargs):
    # Remove any handlers that return False from calling them
    self._handlers = [h for h in self._handlers if h(*args, **kwargs) != False]

EventHook.fire = fire

###################################
#  END patches to signalr-client  #
###################################


class TSLClient(Thread):

    def __init__(self, handler, host="livetiming.tsl-timing.com", sessionID="WebDemo"):
        Thread.__init__(self)
        self.handler = handler
        self.log = handler.log
        self.host = host
        self.sessionID = sessionID
        self.daemon = True

    def run(self):
        with Session() as session:
            connection = Connection("http://{}/signalr/".format(self.host), session)
            hub = connection.register_hub('livetiming')

            def print_error(error):
                print('error: ', error)

            def delegate(method, data):
                handler_method = "on_{}".format(method.lower())
                if hasattr(self.handler, handler_method) and callable(getattr(self.handler, handler_method)):
                    getattr(self.handler, handler_method)(data)
                else:
                    self.log.info("Unhandled message: {}".format(handler_method))
                    self.log.debug("Message content was {}".format(data))

            def handle(**kwargs):
                if 'M' in kwargs:
                    for msg in kwargs['M']:
                        delegate(msg['M'], msg['A'])

            connection.error += print_error
            connection.received += handle

            with connection:
                hub.server.invoke('RegisterConnectionId', self.sessionID, True, False, True)
                hub.server.invoke_then('GetClassification', self.sessionID)(lambda d: delegate('classification', d))
                hub.server.invoke_then('GetSessionData', self.sessionID)(lambda d: delegate('session', d))
                hub.server.invoke_then('GetIntermediatesTimes', self.sessionID)(lambda d: delegate('sectortimes', d))

                connection.wait(None)


def mapState(state, inPit):
    if inPit:
        return "PIT"
    if state == "Running":
        return "RUN"
    if state == "Finished":
        return "FIN"
    if state == "Missing":
        return "?"
    return state


def parseTime(formattedTime):
    if formattedTime == "":
        return 0
    try:
        ttime = datetime.strptime(formattedTime, "%M:%S.%f")
        return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
        return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)


def mapSessionState(state):
    mapping = {
        'Green': FlagStatus.GREEN,
        'Red': FlagStatus.RED,
        'Yellow': FlagStatus.YELLOW,
        'FCY': FlagStatus.FCY,
        'Finished': FlagStatus.CHEQUERED,
        'Complete': FlagStatus.CHEQUERED,
        'Pending': FlagStatus.NONE,
        'Active': FlagStatus.NONE
    }
    if state in mapping:
        return mapping[state]
    print "Unknown flag state: {}".format(state)
    return FlagStatus.NONE


class Service(lt_service):
    def __init__(self, config):
        super(Service, self).__init__(config)
        client = TSLClient(self, host="lt-us.tsl-timing.com", sessionID="171006")
        client.start()

        self.name = "TSL Timing"
        self.description = ""

        self.cars = {}
        self.sectorTimes = {}
        self.trackSectors = {}

        self.flag = FlagStatus.NONE
        self.timeRemaining = -1
        self.timeReference = datetime.utcnow()
        self.lapsRemaining = None
        self.startTime = datetime.utcnow()

        self.weather = {
            'tracktemp': None,
            'trackstate': None,
            'airtemp': None,
            'airpressure': None,
            'windspeed': None,
            'winddir': None,
            'humidity': None
        }

    def getHost(self):
        return "livetiming.tsl-timing.com"

    def getSessionID(self):
        return "WebDemo"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.CLASS,
            Stat.STATE,
            Stat.DRIVER,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP
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
            "Air pressure",
            "Wind speed",
            "Direction",
            "Humidity"
        ]

    def getRaceState(self):
        cars = []

        for car in sorted(self.cars.values(), key=lambda c: c['Pos']):
            cars.append([
                car['StartNumber'],
                car['SubClass'],
                mapState(car['Status'], car['InPits']),
                car['Name'],
                car['Vehicle'],
                car['Laps'],
                car['Gap'],
                car['Diff'],
                "" if car['ID'] not in self.sectorTimes else self.sectorTimes[car["ID"]][0],
                "" if car['ID'] not in self.sectorTimes else self.sectorTimes[car["ID"]][1],
                "" if car['ID'] not in self.sectorTimes else self.sectorTimes[car["ID"]][2],
                (parseTime(car['LastLapTime']), "pb" if car['PersonalBestTime'] else ""),
                (parseTime(car['CurrentSessionBest']), "")
            ])

        now = datetime.utcnow()

        return {
            "cars": cars,
            "session": {
                "flagState": self.flag.name.lower(),
                "timeElapsed": (now - self.startTime).total_seconds(),
                "timeRemain": max(self.timeRemaining - (now - self.timeReference).total_seconds(), 0),
                "trackData": [
                    u"{}°C".format(self.weather['tracktemp']),
                    self.weather['trackstate'],
                    u"{}°C".format(self.weather['airtemp']),
                    "{}mb".format(self.weather['airpressure']),
                    "{}mph".format(self.weather['windspeed']),
                    u"{}°".format(self.weather['winddir']),
                    "{}%".format(self.weather['humidity'])
                ]
            }
        }

    def on_session(self, data):
        if "TrackDisplayName" in data:
            self.name = data["TrackDisplayName"]
        if "Series" in data and "Name" in data:
            if data["Series"] and data["Name"]:
                self.description = "{} - {}".format(data["Series"], data["Name"])
            elif data["Series"]:
                self.description = data["Series"]
            elif data["Name"]:
                self.description = data["Name"]
        if "State" in data:
            self.flag = mapSessionState(data['State'])
        if "TrackConditions" in data:
            self.weather['trackstate'] = data['TrackConditions']
        if "LapsRemaining" in data:
            self.lapsRemaining = data["LapsRemaining"]
        if "TrackSectors" in data:
            for sector in data["TrackSectors"]:
                if sector["Name"][0] == "S" and len(sector["Name"]) == 2:
                    self.trackSectors[sector['ID']] = int(sector["Name"][1]) - 1
        if "ActualStart" in data and "UTCOffset" in data:
            self.startTime = datetime.utcfromtimestamp((data["ActualStart"] - data["UTCOffset"]) / 1e6)
        self.publishManifest()

    def on_classification(self, data):
        for car in data:
            self.cars[car['ID']] = car

    def on_settimeremaining(self, data):
        self.timeRemaining = (60 * (60 * int(data[0]['d'][0]) + int(data[0]['d'][1]))) + int(data[0]['d'][2])
        self.timeReference = datetime.utcnow()

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
        print ">>> updateresult"
        print data
        print "<<<"

    def on_sectortimes(self, data):
        for d in data:
            cid = d["CompetitorID"]
            if cid not in self.sectorTimes:
                self.sectorTimes[cid] = ["", "", ""]
            sector = self.trackSectors.get(d["Id"], -1)
            if sector >= 0:
                self.sectorTimes[cid][sector] = d["Time"] / 1e6
