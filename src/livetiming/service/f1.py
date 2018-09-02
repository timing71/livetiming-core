# -*- coding: utf-8 -*-
from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.racing import FlagStatus, Stat
from livetiming.service import Service as lt_service
from twisted.logger import Logger
from twisted.internet import reactor
from twisted.web import client
from twisted.web.client import Agent, readBody
from requests.sessions import Session
from signalr import Connection
from threading import Thread


import math
import simplejson
import time

client._HTTP11ClientFactory.noisy = False

_web_agent = Agent(reactor)


class F1Client(Thread):
    def __init__(self, handler):
        Thread.__init__(self)
        self.handler = handler
        self.log = handler.log
        self.host = "livetiming.formula1.com"
        self.daemon = True

    def run(self):
        with Session() as session:
            connection = Connection("https://{}/signalr/".format(self.host), session)
            hub = connection.register_hub('streaming')

            def print_error(error):
                print('error: ', error)

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
                if 'R' in kwargs:
                    for msg, payload in kwargs['R'].iteritems():
                        delegate(msg, [msg, payload])
                if 'M' not in kwargs and 'R' not in kwargs:
                    if len(kwargs) > 0:
                        self.log.warn("Unhandled packet: {pkt}", pkt=kwargs)

            connection.error += print_error
            connection.received += handle

            with connection:
                hub.server.invoke('Subscribe', ['SPFeed', 'ExtrapolatedClock'])
                connection.wait(None)


def mapTimeFlag(color):
    timeMap = {
        "P": "sb",
        "G": "pb",
        "Y": "old"
    }
    if color in timeMap:
        return timeMap[color]
    return ""


def renderGapOrLaps(raw):
    if raw != "" and raw[0] == "-":
        laps = -1 * int(raw)
        return "{} lap{}".format(laps, "s" if laps > 1 else "")
    return raw


def parseTyre(tyreChar):
    tyreMap = {
        "D": ("SH", "tyre-shard"),
        "H": ("H", "tyre-hard"),
        "M": ("M", "tyre-med"),
        "S": ("S", "tyre-soft"),
        "V": ("SS", "tyre-ssoft"),
        "E": ("US", "tyre-usoft"),
        "F": ("HS", "tyre-hsoft"),
        "I": ("I", "tyre-inter"),
        "W": ("W", "tyre-wet"),
        "U": ("U", "tyre-development")
    }
    return tyreMap.get(tyreChar, '?')


def parseFlagState(flagChar):
    flagMap = {
        "C": FlagStatus.CHEQUERED,
        "Y": FlagStatus.YELLOW,
        "V": FlagStatus.VSC,
        "S": FlagStatus.SC,
        "R": FlagStatus.RED
    }
    if flagChar in flagMap:
        return flagMap[flagChar].name.lower()
    return "green"


def parse_time(formattedTime):
    if formattedTime == "" or formattedTime is None:
        return 0
    try:
        return float(formattedTime)
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S.%f")
            return (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
        except ValueError:
            try:
                ttime = datetime.strptime(formattedTime, "%H:%M:%S.%f")
                return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
            except ValueError:
                return formattedTime


def obj_to_array(obj):
    try:
        result = []
        for key, val in sorted(obj.iteritems(), key=lambda i: int(i[0])):
            result[int(key)] = val
        return result
    except (ValueError, AttributeError):
        return obj


def array_add(arr, idx, item):
    if idx < len(arr):
        arr[idx] = item
    else:
        while len(arr) < item - 1:
            arr.append(None)
        arr.append(item)


def _apply_patch_children(orig, patch):

    if patch.get('_kf', False):
        if isinstance(orig, list):
            del orig[:]
        elif isinstance(orig, dict):
            for key in orig:
                if key[0] != '_':
                    del orig[key]
        del patch['_kf']

    for name, value in sorted(patch.iteritems(), key=lambda i: i[0]):
        try:
            name = int(name)
        except ValueError:
            name = name
        if name == '_deleted':
            for deletedItem in value:
                del orig[deletedItem]
        else:
            if isinstance(orig, list):
                if isinstance(value, dict):
                    _apply_patch_children(orig[name], value)
                else:
                    # print orig
                    # print "Setting array orig[{}] = {} ({})".format(name, value, type(value))
                    array_add(orig, name, value)
            elif name in orig:
                if value is None:
                    del orig[name]
                elif isinstance(value, dict):
                    _apply_patch_children(orig[name], value)
                else:
                    # print "Setting orig[{}] = {} ({})".format(name, value, type(value))
                    orig[name] = value
            else:
                # print orig, len(orig)
                # print "Creating orig[{}] = {}".format(name, value)
                orig[name] = obj_to_array(value)


class Service(lt_service):
    attribution = ['FOWC', 'https://www.formula1.com/']
    auto_poll = False

    log = Logger()

    def __init__(self, args, extra_args):
        args.hidden = True  # Always hide F1 due to C&D from FOM
        lt_service.__init__(self, args, extra_args)
        self.dataMap = {}
        self._clock = {}
        self.prevRaceControlMessage = -1
        self.messages = []
        self.dataLastUpdated = datetime.now()
        self._commsIndex = None

        self._description = 'Formula 1'

        client = F1Client(self)
        client.start()

    def on_spfeed(self, payload):
        self.on_feed(payload)

    def on_feed(self, payload):
        data = payload[1]
        self._apply_patch(data)

        if 'free' in data:

            free = self._getData('free')

            new_desc = '{} - {}'.format(
                free['R'].title(),
                free['S']
            )

            if new_desc != self._description:
                self._description = new_desc
                self.log.info("New session: {desc}", desc=new_desc)
                self.publishManifest()

        comms = self._getData('commentary')
        pd = comms.get('PD', [])
        if len(pd) > 0:
            if 'h' in pd[0]:
                idx = pd[0]['h']
                if self._commsIndex != idx:
                    self._fetch_comms(idx)

        self.dataLastUpdated = datetime.now()
        self._updateAndPublishRaceState()

    def _apply_patch(self, patch):
        _apply_patch_children(self.dataMap, patch)

    def on_extrapolatedclock(self, clock):
        _apply_patch_children(self._clock, clock[1])

    def _fetch_comms(self, idx):
        if 'path' in self.dataMap:
            comms_url = 'https://livetiming.formula1.com/static/{}com.rc.js?{}'.format(self.dataMap['path'], idx)

            def handle_comms(comms):
                comm_json = simplejson.loads(comms[5:-2])
                msgs = filter(lambda m: m['id'] > self.prevRaceControlMessage and (m['type'] == 'RCM' or '_FLAG' in m['type']), comm_json['feed']['e'])
                for msg in msgs:
                    self.messages.append([msg['pub'], msg['text']])
                    self.prevRaceControlMessage = max(self.prevRaceControlMessage, msg['id'])

            def handle_comm_response(resp):
                d = readBody(resp)
                d.addCallback(handle_comms)

            req = _web_agent.request(
                'GET',
                comms_url
            )
            req.addCallback(handle_comm_response)

        self._commsIndex = idx

    def getName(self):
        return "Formula 1"

    def getDefaultDescription(self):
        return self._description

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.DRIVER,
            Stat.LAPS,
            Stat.TYRE,
            Stat.TYRE_STINT,
            Stat.TYRE_AGE,
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
            Stat.PITS
        ]

    def getTrackDataSpec(self):
        return [
            "Track Temp",
            "Air Temp",
            "Wind Speed",
            "Direction",
            "Humidity",
            "Pressure",
            "Track",
            "Updated"
        ]

    def getPollInterval(self):
        return 1

    def _getData(self, key, subkey=None):
        if key in self.dataMap:
            if 'data' in self.dataMap[key]:
                if subkey is not None:
                        return self.dataMap[key]['data'].get(subkey)
                return self.dataMap[key]['data']
            else:
                return self.dataMap[key]

        return None

    def getRaceState(self):
        # print self.dataMap.keys()

        if 'free' not in self.dataMap:
            self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
            return {
                'cars': [],
                'session': {
                    "flagState": "none",
                    "timeElapsed": 0,
                    "timeRemain": -1
                }
            }

        cars = []
        drivers = []
        bestTimes = []
        flag = None

        init = self._getData("init")
        if init:
            drivers = init["Drivers"]
            startTime = init.get("ST", None)

        currentTime = self._getData("cpd", "CT")
        if currentTime is None:
            currentTime = time.time() * 1000

        b = self._getData("best")
        if b:
            bestTimes = b["DR"]
            flag = b["F"]

        latestTimes = self._getData("opt", "DR")

        sq = self._getData("sq", "DR")

        extra = self._getData("xtra", "DR")

        free = self._getData('free')

        denormalised = []

        for idx, driver in enumerate(drivers):
            dnd = {}
            dnd["driver"] = driver
            dnd["timeLine"] = bestTimes[idx]["B"]
            if "STOP" in bestTimes[idx]:
                dnd["stop"] = bestTimes[idx]["STOP"]
            dnd["latestTimeLine"] = latestTimes[idx]["O"]
            dnd["sq"] = sq[idx]["G"]
            dnd["extra"] = extra[idx]
            denormalised.append(dnd)

        fastestLap = min(map(lambda d: parse_time(d["timeLine"][1]) if d["timeLine"][1] != "" else 9999, denormalised))

        for dnd in sorted(denormalised, key=lambda d: int(d["latestTimeLine"][4])):
            driver = dnd["driver"]
            latestTimeLine = dnd["latestTimeLine"]
            timeLine = dnd["timeLine"]
            colorFlags = dnd["latestTimeLine"][2]
            sq = dnd["sq"]

            if "X" in dnd["extra"] and dnd["extra"]["X"][9] != "":
                currentTyre = parseTyre(dnd["extra"]["X"][9][0])
                currentTyreStats = dnd["extra"]["TI"][-2:]
            else:
                currentTyre = ""
                currentTyreStats = ("", "", "")

            state = "RUN"
            if latestTimeLine[3][2] == "1":
                state = "PIT"
            elif latestTimeLine[3][2] == "2":
                state = "OUT"
            elif latestTimeLine[3][2] == "3":
                state = "STOP"

            fastestLapFlag = ""
            if timeLine[1] != "" and fastestLap == parse_time(timeLine[1]):
                fastestLapFlag = "sb-new" if timeLine[1] == latestTimeLine[1] and state == "RUN" else "sb"

            gap = renderGapOrLaps(latestTimeLine[9])
            interval = renderGapOrLaps(latestTimeLine[14])

            if gap == "" and len(cars) > 0 and timeLine[1] != "":
                fasterCarTime = cars[-1][16][0] or 0
                fastestCarTime = cars[0][16][0] or 0
                ourBestTime = parse_time(timeLine[1])
                interval = ourBestTime - fasterCarTime
                gap = ourBestTime - fastestCarTime

            last_lap = parse_time(latestTimeLine[1])

            cars.append([
                driver["Num"],
                state,
                driver["FullName"].title(),
                math.floor(float(sq[0])) if sq[0] else 0,
                currentTyre,
                currentTyreStats[0] if len(currentTyreStats) > 0 else '?',
                currentTyreStats[1] if len(currentTyreStats) > 1 else '?',
                gap,
                interval,
                [latestTimeLine[5], mapTimeFlag(colorFlags[1])],
                [timeLine[4], 'old'],
                [latestTimeLine[6], mapTimeFlag(colorFlags[2])],
                [timeLine[7], 'old'],
                [latestTimeLine[7], mapTimeFlag(colorFlags[3])],
                [timeLine[10], 'old'],
                [last_lap if last_lap > 0 else '', "sb-new" if fastestLapFlag == "sb-new" else mapTimeFlag(colorFlags[0])],
                [parse_time(timeLine[1]), fastestLapFlag] if timeLine[1] != "" else ['', ''],
                latestTimeLine[3][0]
            ])

        currentLap = free["L"]
        totalLaps = free["TL"]

        lapsRemain = max(totalLaps - currentLap + 1, 0)

        session = {
            "flagState": parseFlagState(free["FL"] if flag is None else flag),
            "timeElapsed": (currentTime - startTime) / 1000 if startTime else 0,
            "timeRemain": self._getTimeRemaining(),
            "trackData": self._getTrackData()
        }

        if "S" in free and free["S"] == "Race":
            session["lapsRemain"] = math.floor(lapsRemain)

        state = {
            "cars": cars,
            "session": session,
        }

        return state

    def _getTimeRemaining(self):
        if 'Remaining' in self._clock:
            remaining_parts = map(int, self._clock['Remaining'].split(':'))
            remaining = remaining_parts[2] + (60 * remaining_parts[1]) + (3600 * remaining_parts[0])

            if self._clock.get('Extrapolating', False):
                timestamp = datetime.strptime(
                    self._clock['Utc'][:-2],
                    "%Y-%m-%dT%H:%M:%S.%f"
                )

                offset = (datetime.utcnow() - timestamp).total_seconds()
                return remaining - offset

            else:
                return remaining

        return None

    def _getTrackData(self):
        W = self._getData("sq", "W")
        if W:
            w = W
            return [
                u"{}°C".format(w[0]),
                u"{}°C".format(w[1]),
                "{}m/s".format(w[3]),
                u"{}°".format(float(w[6])),
                "{}%".format(w[4]),
                "{} mbar".format(w[5]),
                "Wet" if w[2] == "1" else "Dry",
                self.dataLastUpdated.strftime("%H:%M:%S")
            ]
        return []

    def getExtraMessageGenerators(self):
        return [
            TimestampedRaceControlMessage(self.messages)
        ]


class TimestampedRaceControlMessage(RaceControlMessage):
    def process(self, oldState, newState):
        msgs = []
        while len(self.messageList) > 0:
            ts, nextMessage = self.messageList.pop()
            hasCarNum = self.CAR_NUMBER_REGEX.search(nextMessage)
            if hasCarNum:
                msgs.append([ts, "Race Control", nextMessage.upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([ts, "Race Control", nextMessage.upper(), "raceControl"])
        return msgs
