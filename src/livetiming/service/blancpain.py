from livetiming.service import Service as lt_service, JSONFetcher
import argparse
import simplejson
import urllib2
from twisted.internet import reactor
import time
from livetiming.racing import Stat, FlagStatus
from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.analysis.lapchart import LapChart
from livetiming.analysis.pits import EnduranceStopAnalysis
from livetiming.analysis.driver import StintLength
from livetiming.analysis.session import Session


SRO_ROOT_URL = "http://livecache.sportresult.com/node/db/RA_PROD/SRO_2017_SEASON_JSON.json?s=3&t=0"
SRO_SCHEDULE_URL = "http://livecache.sportresult.com/node/db/RA_PROD/SRO_2017_SCHEDULE_{meeting}_JSON.json"
SRO_SESSION_TIMING_URL = "http://livecache.sportresult.com/node/db/RA_PROD/SRO_2017_TIMING_{session}_JSON.json"
SRO_SESSION_DATA_URL = "http://livecache.sportresult.com/node/db/RA_PROD/SRO_2017_COMP_DETAIL_{session}_JSON.json"


STATE_LIVE = 1
TYPE_AGGREGATE = 3


def json_get(url):
    try:
        return simplejson.load(urllib2.urlopen(url))
    except simplejson.JSONDecodeError:
        return None


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", help="Meeting ID")
    parser.add_argument("--session", help="Session ID")

    return parser.parse_known_args(args)


def uncache(url):
    def inner():
        if "?" in url:
            return "{}&t={}".format(url, int(time.time()))
        return "{}?t={}".format(url, int(time.time()))
    return inner


def map_car_state(raw_state, in_pit):
    if in_pit:
        return 'PIT'
    state_map = {
        0: '?',
        1: 'FIN',
        2: 'RUN',
        4: 'RET',
        16: 'RET',
        32: 'N/S'
    }
    if raw_state in state_map:
        return state_map[raw_state]
    return str(raw_state)


def parse_time(formattedTime):
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


def parse_session_time(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S")
        return (3600 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S")
            return (60 * ttime.minute) + ttime.second
        except ValueError:
            return formattedTime


def parse_sro_date(formattedDate):
    try:
        return datetime.strptime(formattedDate, "%d.%m.%Y %H:%M:%S.%f")
    except ValueError:
        return None


def map_time_flags(flag):
    flags = {
        0: '',
        1: 'pb',
        2: 'sb'
    }
    if flag in flags:
        return flags[flag]
    return 'flag{}'.format(flag)


def parse_time_data(i):
    if "Time" in i:
        return (parse_time(i['Time']), map_time_flags(i['TimeState']))
    return ('', '')


def map_session_flag(data):
    if data['ChequeredFlag']:
        return FlagStatus.CHEQUERED.name.lower()

    if data['TrackFlag'] == 4:
        # Track flag yellow means FCY; local yellows are in SectorFlags
        return FlagStatus.FCY.name.lower()

    flag_map = {
        0: FlagStatus.NONE,
        1: FlagStatus.GREEN,
        4: FlagStatus.YELLOW,
        8: FlagStatus.RED,
        32: FlagStatus.SC,
        64: FlagStatus.CODE_60,
        268435456: FlagStatus.NONE
    }

    flag = 0
    if 'SectorFlags' in data:
        flag = max(data['SectorFlags'])

    flag = max(flag, data['TrackFlag'])

    if flag in flag_map:
        return flag_map[flag].name.lower()
    return 'none'


class Service(lt_service):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.extra_args = extra_args

        self._timing_data = None
        self._session_data = None
        self._messages = []
        self.mostRecentMessage = None

        self.name = None
        self.description = None

        self._init_session()

    def _init_session(self):
        ea, _ = parse_extra_args(self.extra_args)

        self.sro_session, self.name, self.description = self._find_session(ea.meeting, ea.session)

        if self.sro_session:
            self._previous_laps = {}

            session_fetcher = JSONFetcher(uncache(SRO_SESSION_DATA_URL.format(session=self.sro_session)), self._receive_session, 20)
            session_fetcher.start()

            timing_fetcher = JSONFetcher(uncache(SRO_SESSION_TIMING_URL.format(session=self.sro_session)), self._receive_timing, 2)
            timing_fetcher.start()

        else:
            self.log.info("No session found, checking again in 30 seconds.")
            reactor.callLater(30, self._init_session)

    def _find_meeting(self, meetingID=None):
        meetings_json = json_get(SRO_ROOT_URL)
        if meetings_json:
            meetings = meetings_json['content']['full']['Meetings']
            if meetingID and meetingID.lower() in meetings:
                self.log.info("Found requested meeting {meetingID}", meetingID=meetingID.lower())
                return meetings[meetingID.lower()]
            else:
                live_meetings = [m for m in meetings.values() if m['State'] == STATE_LIVE]
                if live_meetings:
                    self.log.info("Using currently live meeting {meetingID}", meetingID=live_meetings[0]['Id'].lower())
                    return live_meetings[0]
        self.log.warn("Could not find a live meeting!")
        return None

    def _find_session(self, meetingID=None, sessionID=None):
        meeting = self._find_meeting(meetingID)
        if meeting:
            sessions_json = json_get(SRO_SCHEDULE_URL.format(meeting=meeting['Id'].upper()))
            if sessions_json:
                sessions = sessions_json['content']['full']['Units']
                session = None
                if sessionID and sessionID.lower() in sessions:
                    self.log.info("Found requested session {sessionID}", sessionID=sessionID.lower())
                    session = sessions[sessionID]
                else:
                    live_sessions = [s for s in sessions.values() if s['State'] == STATE_LIVE and s['Type'] != TYPE_AGGREGATE]
                    if live_sessions:
                        self.log.info("Using live session {sessionID}", sessionID=live_sessions[-1]['Id'].lower())
                        session = live_sessions[-1]
                if session:
                    return session['Id'].upper(), \
                        sessions_json['content']['full']['Competitions'][session['CompetitionId']]['Name'], \
                        session['Name']
        self.log.warn("Could not find a live session!")
        return None, None, None

    def no_service_state(self):
        self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
        return {
            'cars': [],
            'session': {
                "flagState": "none",
                "timeElapsed": 0
            }
        }

    def _receive_session(self, data):
        self.log.debug("Received session data")
        self._session_data = data['content']['full']

        if 'Messages' in self._session_data:
            for message in self._session_data['Messages']:
                msg_time = datetime.strptime(message['Time'], "%d.%m.%Y %H:%M:%S")
                if not self.mostRecentMessage or self.mostRecentMessage < msg_time:
                    self._messages.append(message['Text'])
                    self.mostRecentMessage = msg_time

    def _receive_timing(self, data):
        self.log.debug("Received timing data")
        self._timing_data = data['content']['full']

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.DRIVER,
            Stat.CAR,
            Stat.TEAM,
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

    def getPollInterval(self):
        return 10

    def getName(self):
        return self.name if self.name else "Blancpain GT"

    def getDefaultDescription(self):
        return self.description if self.description else "Blancpain GT"

    def getRaceState(self):
        if self.sro_session:
            if self._session_data and self._timing_data:
                return self._compile_state()
        return self.no_service_state()

    def getExtraMessageGenerators(self):
        return [RaceControlMessage(self._messages)]

    def getAnalysisModules(self):
        return [
            Session,
            LapChart,
            EnduranceStopAnalysis,
            StintLength
        ]

    def _compile_state(self):
        cars = []

        for entry in sorted(self._timing_data['Results'].values(), key=lambda e: e['ListIndex']):
            competitor = self._session_data['Competitors'][entry['CompetitorId']]
            driver = competitor['Drivers'][competitor['CurrentDriverId']] if 'CurrentDriverId' in competitor and competitor['CurrentDriverId'] in competitor['Drivers'] else None
            if 'ClassId' in competitor:
                clazz = self._session_data['Classes'][competitor['ClassId']]['ShortName'] if competitor['ClassId'] in self._session_data['Classes'] else competitor['ClassId']
            else:
                clazz = ''

            main_result = entry['MainResult']

            cars.append([
                competitor['Bib'],
                map_car_state(main_result['Status'], competitor['InPitLane']),
                clazz,
                u"{}, {}".format(driver['LastName'].upper(), driver['FirstName']) if driver else '',
                competitor['CarTypeName'],
                competitor['TeamShortName'] if 'TeamShortName' in competitor else competitor['TeamName'] if 'TeamName' in competitor else '',
                main_result['TotalLapCount'] if 'TotalLapCount' in main_result else 0,
                main_result['Behind'] if 'Behind' in main_result else '',
                main_result['Diff'] if 'Diff' in main_result else '',
                parse_time_data(main_result['LastLap']['Intermediates'][0]) if 'LastLap' in main_result else ('', ''),
                parse_time_data(main_result['LastLap']['Intermediates'][1]) if 'LastLap' in main_result else ('', ''),
                parse_time_data(main_result['LastLap']['Intermediates'][2]) if 'LastLap' in main_result else ('', ''),
                parse_time_data(main_result['LastLap']) if 'LastLap' in main_result else ('', ''),
                parse_time_data(main_result['BestTime']) if 'BestTime' in main_result else ('', ''),
                competitor['PitStopCount'] if 'PitStopCount' in competitor else 0
            ])

            # Hack in previous lap before it disappears from the data feed
            if cars[-1][12][0] == '':
                cars[-1][12] = self._previous_laps.get(competitor['Bib'], ('', ''))
            else:
                self._previous_laps[competitor['Bib']] = cars[-1][12]

        unt = self._timing_data['UntInfo']

        session = {
            'flagState': map_session_flag(unt),
            'timeRemain': parse_session_time(unt['RemainingTime']),
            'timeElapsed': (datetime.utcnow() - parse_sro_date(unt['StartRealTime'])).total_seconds() if 'StartRealTime' in unt else 0  # Let's just assume UTC here
        }

        return {'cars': cars, 'session': session}