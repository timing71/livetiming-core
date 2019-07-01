from datetime import datetime
from livetiming.messages import RaceControlMessage
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service, DuePublisher
from livetiming.service.swisstiming.client import create_client, start_client

import argparse
import time


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", help="Meeting ID")
    parser.add_argument("--session", help="Session ID")
    parser.add_argument("--tz", type=int, help='Timezone offset in minutes from UTC', default=0)

    return parser.parse_known_args(args)


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


STATE_LIVE = 1
TYPES_AGGREGATE = [3, 6]


class Service(DuePublisher, lt_service):
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.extra_args = parse_extra_args(extra_args)[0]

        if not hasattr(self, 'namespace'):
            raise Exception("{} does not declare a namespace. Fix your code!".format(self.__module__))
        if not hasattr(self, 'profile'):
            raise Exception("{} does not declare a profile. Fix your code!".format(self.__module__))

        self.session = None
        self.schedule = None
        self.meeting = None

        self._session_data = None
        self._timing_data = None
        self._rc_messages = RaceControlMessage([])
        self._last_msg_time = -1
        self._previous_laps = {}

        client_def = create_client(self.namespace, self.profile, self._load_season, self.log)
        self._client = start_client(client_def)

    def _load_season(self, data):
        self._client.get_current_season(self._handle_season)

    def _handle_season(self, season):
        meetingID = self.extra_args.meeting
        self.meeting = None

        meetings = season['Meetings']
        if meetingID and meetingID.lower() in meetings:
            self.log.info(
                "Found requested meeting {meetingID}: {name}",
                meetingID=meetingID.lower(),
                name=meetings[meetingID.lower()]['Name']
            )
            self.meeting = meetings[meetingID.lower()]
            self._client.get_schedule(meetingID, self._handle_schedule)
        else:
            live_meetings = [m for m in list(meetings.values()) if m['State'] == STATE_LIVE]
            if live_meetings:
                self.log.info(
                    "Using currently live meeting {meetingID}: {name}",
                    meetingID=live_meetings[0]['Id'].lower(),
                    name=live_meetings[0]['Name']
                )
                self.meeting = live_meetings[0]
                self._client.get_schedule(self.meeting['Id'], self._handle_schedule)

        if not self.meeting:
            self.log.warn("Could not find a live meeting!")

    def _handle_schedule(self, schedule):
        self.schedule = schedule
        sessions = schedule['Units']
        sessionID = self.extra_args.session

        prev_session = self.session
        new_session = None

        if sessionID and sessionID.lower() in sessions:
            new_session = sessions[sessionID.lower()]
            self.log.info(
                "Found requested session {sessionID}: {name}",
                sessionID=sessionID.lower(),
                name=new_session['Name']
            )

        else:
            live_sessions = [s for s in list(sessions.values()) if s['State'] == STATE_LIVE and s['Type'] not in TYPES_AGGREGATE]
            if live_sessions:
                new_session = live_sessions[-1]

        if new_session:
            self.session = new_session
            if prev_session:
                if prev_session['Id'] != self.session['Id']:
                    self.log.info("Changing session from {old} to {new}", old=prev_session, new=self.session)
                    self.analyser.reset()
                    self._previous_laps = {}
                    self._session_data = None
                    self._timing_data = None
            else:
                self.log.info(
                    "Using live session {sessionID}: {name}",
                    sessionID=self.session['Id'].lower(),
                    name=self.session['Name']
                )
            self._client.get_timing(self.session['Id'], self._handle_timing)
            self._client.get_comp_detail(self.session['Id'], self._handle_session)
            self.publishManifest()

        elif self.session:
            self.log.info('No live session detected, maintaining current session.')
        else:
            self.log.warn(
                'No live sessions detected and no session specified. Available sessions: {sessions}',
                sessions=list(sessions.keys())
            )

    def _handle_timing(self, data):
        self._timing_data = data
        self.set_due_publish()

    def _handle_session(self, data):
        self._session_data = data

        rc_messages = [m for m in data.get('Messages', []) if m['Time'] > self._last_msg_time]
        for m in rc_messages:
            self._rc_messages.messageList.append(m['Text'])
            self._last_msg_time = max(self._last_msg_time, m['Time'])

        self.set_due_publish()

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
        return 1

    def getName(self):
        if self.schedule and self.session:
            return self.schedule['Competitions'][self.session['CompetitionId']]['Name']
        return self.default_name

    def getDefaultDescription(self):
        if self.meeting and self.session:
            return "{} - {}".format(self.meeting['Name'], self.session['Name'])
        return ''

    def _no_service_state(self):
        self.state['messages'] = [[int(time.time()), "System", "Currently no live session", "system"]]
        return {
            'cars': [],
            'session': {
                "flagState": "none",
                "timeElapsed": 0
            }
        }

    def getRaceState(self):
        if self.session:
            if self._session_data and self._timing_data:
                return self._compile_state()
        return self._no_service_state()

    def getExtraMessageGenerators(self):
        return [self._rc_messages]

    def _compile_state(self):
        cars = []

        for entry in sorted(list(self._timing_data['Results'].values()), key=lambda e: e.get('ListIndex', 9999)):
            if 'CompetitorId' in entry:
                competitor = self._session_data['Competitors'].get(entry['CompetitorId'])
                if competitor:
                    driver = competitor['Drivers'][competitor['CurrentDriverId']] if 'CurrentDriverId' in competitor and competitor['CurrentDriverId'] in competitor['Drivers'] else None
                    if 'ClassId' in competitor:
                        clazz = self._session_data['Classes'][competitor['ClassId']].get('ShortName', '') if competitor['ClassId'] in self._session_data['Classes'] else competitor['ClassId']
                    else:
                        clazz = ''

                    main_result = entry['MainResult']

                    cars.append([
                        competitor['Bib'],
                        map_car_state(main_result['Status'], competitor['InPitLane']),
                        clazz,
                        "{}, {}".format(driver['LastName'].upper(), driver['FirstName']) if driver else '',
                        competitor.get('CarTypeName', ''),
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
                else:
                    self.log.warn('Unknown competitor for entry {entry}', entry=entry)
            else:
                self.log.warn('Unknown competitor for entry {entry}', entry=entry)

        unt = self._timing_data['UntInfo']

        session = {
            'flagState': map_session_flag(unt),
            'timeRemain': parse_session_time(unt['RemainingTime']),
            'timeElapsed': (datetime.utcnow() - parse_sro_date(unt['StartRealTime'])).total_seconds() + (60 * self.extra_args.tz) if 'StartRealTime' in unt else 0
        }

        return {'cars': cars, 'session': session}
