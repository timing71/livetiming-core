from collections import defaultdict
from livetiming.messages import TimingMessage, CAR_NUMBER_REGEX
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service
from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import LoopingCall

import argparse
import inspect
import simplejson
import time

END_OF_MESSAGE = '<EOM>'


def handler(*msg_types):
    def inner(func):
        func.handles_message = msg_types
        return func
    return inner


def update_present_values(source, destination):
    for key, val in source.iteritems():
        if val != -1:
            destination[key] = val


def create_protocol(service, initial_state_file=None):
    class HHProtocol(Protocol):
        def log(self, *args, **kwargs):
            if service:
                service.log.info(*args, **kwargs)
            else:
                print args, kwargs

        def connect(self, endpoint):
            self.log("Connecting to HH Timing at {endpoint}...", endpoint=endpoint)
            return connectProtocol(endpoint, self)

        def connectionMade(self):
            self.cars = defaultdict(dict)
            self.track = {}
            self.session = {}
            self.messages = []
            self._buffer = ''

            self._handlers = {}

            for name, func in inspect.getmembers(self, predicate=inspect.ismethod):
                if hasattr(func, 'handles_message'):
                    for msg_type in func.handles_message:
                        self._handlers[msg_type] = func

        def dump_data(self):
            return {
                'cars': self.cars,
                'track': self.track,
                'session': self.session,
                'messages': self.messages
            }

        def dataReceived(self, data):
            self._buffer += data
            while END_OF_MESSAGE in self._buffer:
                msg, _, rest = self._buffer.partition(END_OF_MESSAGE)
                self.handleMessage(msg)
                self._buffer = rest

        def handleMessage(self, msg):
            parsed_msg = simplejson.loads(msg)
            msg_type = parsed_msg.pop('$type').split(',')[0]

            if msg_type in self._handlers:
                self._handlers[msg_type](parsed_msg)
            else:
                print 'Unhandled message type {}'.format(msg_type)
                print parsed_msg
                print '----'
            if service:
                service.notify_update()

        @handler('HTiming.Core.Definitions.Communication.Messages.HeartbeatMessage')
        def heartbeat(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler('HTiming.Core.Definitions.Communication.Messages.CompetitorMessage')
        def competitor(self, data):
            car = self.cars[data['CompetitorID']]
            update_present_values(data, car)

        @handler('HTiming.Core.Definitions.Communication.Messages.DriverMessage')
        def driver(self, data):
            if data.pop('IsInCar'):
                car = self.cars[data.pop('CarID')]
                car['driver'] = data

        @handler('HTiming.Core.Definitions.Communication.Messages.AdvSectorTimeLineCrossing')
        def adv_sector_crossing(self, data):
            car = self.cars[data.pop('CompetitorNumber')]
            current_sectors = car.setdefault('current_sectors', {})
            sector_index = data.pop('TimelineNumber')
            current_sectors[sector_index] = data
            car['InPit'] = False

            pb_sectors = car.setdefault('PersonalBestSectors', {})
            if sector_index in pb_sectors:
                pb_sectors[sector_index] = min(data['SectorTime'], pb_sectors[sector_index])
            else:
                pb_sectors[sector_index] = data['SectorTime']

        @handler('HTiming.Core.Definitions.Communication.Messages.EventMessage')
        def event(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler('HTiming.Core.Definitions.Communication.Messages.SessionInfoMessage')
        def session_info(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler('HTiming.Core.Definitions.Communication.Messages.AdvTrackInformationMessage')
        def adv_track_info(self, data):
            update_present_values(data, self.track)

        @handler('HTiming.Core.Definitions.Communication.Messages.LaptimeResultsUpdateMessage')
        def laptime_results_update(self, data):
            car = self.cars[data.pop('CarID')]
            update_present_values(data, car)

        @handler('HTiming.Core.Definitions.Communication.Messages.BasicTimeCrossingMessage')
        def basic_time_crossing(self, data):
            car = self.cars[data.pop('CarID')]
            update_present_values(data, car)
            car['previous_sectors'] = car.get('current_sectors', {})
            car['current_sectors'] = {}
            car['OutLap'] = False
            car['InPit'] = False

        @handler('HTiming.Core.Definitions.Communication.Messages.PitInMessage')
        def pit_in(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = True
            car['OutLap'] = False

        @handler('HTiming.Core.Definitions.Communication.Messages.PitOutMessage')
        def pit_out(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = False
            car['OutLap'] = True

        @handler('HTiming.Core.Definitions.Communication.Messages.GeneralRaceControlMessage')
        def race_control_message(self, data):
            self.messages.append((data['MessageReceivedTime'], data['MessageString']))

        @handler(
            'HHTiming.Core.Definitions.Communication.Messages.CarGpsPointMessage',
            'HTiming.Core.Definitions.Communication.Messages.InternalHHHeartbeatMessage',
            'HTiming.Core.Definitions.Communication.Messages.ClassInformationMessage'  # <- this one is pointless so long as ID == description
        )
        def ignore(self, _):
            pass

    protocol = HHProtocol()

    if initial_state_file:
        try:
            with open(initial_state_file, 'r') as statefile:
                state = simplejson.load(statefile)
                protocol.cars = state['cars']
                protocol.session = state['session']
                protocol.track = state['track']
                protocol.messages = state['messages']
        except IOError:
            pass

    return protocol


# 2019-03-13T20:00:09+0000 Unhandled message type HTiming.Core.Definitions.Communication.Messages.GeneralRaceControlMessage
# 2019-03-13T20:00:09+0000 {'MessageReceivedTime': 3608.065999984741, 'MessageString': 'CAR 50 REPORTED TO THE STEWARD FOR NOT RESPECTING THE RED FLAG PROCEDURE'}


class RaceControlMessage(TimingMessage):

    def __init__(self, protocol):
        self.protocol = protocol
        self._mostRecentTimestamp = 0

    def process(self, _, __):

        new_messages = [m for m in self.protocol.messages if m[0] > self._mostRecentTimestamp]

        msgs = []

        for msg in sorted(new_messages, key=lambda m: m[0]):
            hasCarNum = self.CAR_NUMBER_REGEX.search(msg[1])
            msgDate = time.time() * 1000
            if hasCarNum:
                msgs.append([msgDate / 1000, "Race Control", msg['message'].upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([msgDate / 1000, "Race Control", msg['message'].upper(), "raceControl"])

            self._mostRecentTimestamp = max(self._mostRecentTimestamp, map(lambda m: m[0], new_messages))
        return sorted(msgs, key=lambda m: -m[0])


def _map_car_state(car):
    if car.get('OutLap', False):
        return 'OUT'
    elif car.get('InPit', True):
        return 'PIT'
    else:
        return 'RUN'


FLAG_STATE_MAP = {
    0: FlagStatus.NONE,
    2: FlagStatus.RED,
    3: FlagStatus.CHEQUERED,
    5: FlagStatus.GREEN
}


def _extract_sector(sectorIndex, car, num, best_in_class):
    current_sectors = car.get('current_sectors', {})
    previous_sectors = car.get('previous_sectors', {})
    pb_sectors = car.get('PersonalBestSectors', {})
    best = best_in_class.get(sectorIndex)

    sector = str(sectorIndex)

    if sector in current_sectors:
        sector_time = current_sectors[sector]['SectorTime']

        if best and best[1] == num and best[0] == sector_time:
            flag = 'sb'
        elif sector in pb_sectors and pb_sectors[sector] == sector_time:
            flag = 'pb'
        else:
            flag = ''

        return (sector_time, flag)
    elif sector in previous_sectors:
        return (previous_sectors[sector]['SectorTime'], 'old')
    else:
        return ('', '')


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="HH host", default='live-api.hhtiming.com')
    parser.add_argument("--port", help="HH port", type=int, default=24688)

    a, _ = parser.parse_known_args(extra_args)
    return a


def calculate_practice_gap(first, second):
    if first and second and first.get('BestLapTime', 0) > 0 and second.get('BestLapTime', 0) > 0:
        return second['BestLapTime'] - first['BestLapTime']
    return ''


def calculate_race_gap(first, second):
    return ''


class Service(lt_service):
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.protocol = create_protocol(self, self._state_dump_file())
        self._extra_args = parse_extra_args(extra_args)

        self._rcMessageGenerator = RaceControlMessage(self.protocol)

        self._due_publish_state = False
        self._last_update = time.time()

    def _state_dump_file(self):
        return 'hhtiming_state_dump_{}.json'.format(self.uuid)

    def notify_update(self):
        self._last_update = time.time()
        self._due_publish_state = True

        with open(self._state_dump_file(), 'w') as outfile:
            simplejson.dump(
                self.protocol.dump_data(),
                outfile,
                sort_keys=True,
                indent='  '
            )

    def start(self):
        def maybePublish():
            if self._due_publish_state:
                self._updateAndPublishRaceState()
                self._due_publish_state = False
        LoopingCall(maybePublish).start(1)

        self.protocol.connect(
            TCP4ClientEndpoint(
                reactor,
                self._extra_args.host,
                self._extra_args.port
            )
        )

        super(Service, self).start()

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.TEAM,
            Stat.DRIVER,
            Stat.CAR,
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
            Stat.PITS
        ]

    def getName(self):
        return self.protocol.session.get('EventName', 'Live Timing')

    def getDefaultDescription(self):
        return self.protocol.session.get('SessionDescription')

    def getRaceState(self):
        return {
            'cars': self._map_cars(),
            'session': self._map_session()
        }

    def getExtraMessageGenerators(self):
        return [
            self._rcMessageGenerator
        ]

    def _car_sort_function(self):
        if self.protocol.session.get('SessionType') < 3:
            return lambda (num, car): car.get('BestLaptime', int(car.get('CompetitorNumber', 0)))
        else:
            return lambda (num, car): 'FIX ME SOMEHOW'

    def _gap_function(self):
        if self.protocol.session.get('SessionType') < 3:
            return calculate_practice_gap
        else:
            return calculate_race_gap

    def _map_cars(self):
        cars = []

        best_by_class = defaultdict(dict)

        for num, car in self.protocol.cars.iteritems():
            clazz = car.get('CategoryID')
            best_lap = car.get('BestLaptime', None)
            existing_best = best_by_class[clazz].get(0, None)
            if best_lap and (not existing_best or existing_best[0] > best_lap):
                best_by_class[clazz][0] = (best_lap, num)
            for s in range(3):
                sector = str(s + 1)
                best_sector = car.get('PersonalBestSectors', {}).get(sector, None)
                existing_best_sector = best_by_class[clazz].get(s + 1, None)
                if best_sector and (not existing_best_sector or existing_best_sector[0] > best_sector):
                    best_by_class[clazz][s + 1] = (best_sector, num)

        gap_func = self._gap_function()

        for num, car in sorted(self.protocol.cars.iteritems(), key=self._car_sort_function()):
            # print car
            driver = car.get('driver', {})
            clazz = car.get('CategoryID')

            leader = cars[0] if len(cars) > 0 else None
            prev_car = cars[-1] if len(cars) > 0 else None

            car_data = [
                num,
                _map_car_state(car),
                clazz,
                car.get('TeamName'),
                u"{} {}".format(driver.get('FirstName', ''), driver.get('LastName', '')).strip(),
                car.get('CarMake'),
                car.get('NumberOfLaps'),
                gap_func(leader, car),
                gap_func(prev_car, car)
            ]

            for s in range(3):
                car_data.append(
                    _extract_sector(
                        s + 1,
                        car,
                        num,
                        best_by_class[clazz]
                    )
                )

                car_data.append(
                    (car.get('PersonalBestSectors', {}).get(str(s + 1), ''), '')
                )

            last_lap = car.get('LapTime', '')
            best_lap = car.get('BestLaptime', '')
            best_lap_in_class = best_by_class[clazz].get(0)

            if best_lap_in_class and num == best_lap_in_class[1]:
                best_lap_flag = 'sb-new' if last_lap == best_lap else 'sb'
            else:
                best_lap_flag = ''

            car_data += [
                (last_lap, 'pb' if last_lap == best_lap and best_lap != '' else ''),
                (best_lap, best_lap_flag)
            ]

            cars.append(car_data)
        return cars

    def _map_session(self):
        hhs = self.protocol.session
        # print hhs
        delta = time.time() - hhs['LastUpdate']
        session = {
            'flagState': FLAG_STATE_MAP.get(hhs.get('TrackStatus', 0), FlagStatus.NONE).name.lower(),
            'timeElapsed': hhs.get('SessionTime', 0) + delta
        }

        if hhs.get('TimeToGo'):
            session['timeRemain'] = hhs['TimeToGo']

        return session


if __name__ == '__main__':
    hh = create_protocol(None)
    hh.connect(TCP4ClientEndpoint(reactor, 'live-api.hhtiming.com', 24688))
    reactor.run()
