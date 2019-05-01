from collections import defaultdict
from livetiming.messages import TimingMessage, CAR_NUMBER_REGEX
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service
from livetiming.service.hhtiming import create_protocol
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.task import LoopingCall

import argparse
import simplejson
import time


class RaceControlMessage(TimingMessage):

    def __init__(self, protocol):
        self.protocol = protocol
        self._mostRecentTimestamp = 0

    def process(self, _, __):

        new_messages = [m for m in self.protocol.messages if m[0] > self._mostRecentTimestamp]

        msgs = []

        for msg in sorted(new_messages, key=lambda m: m[0]):
            hasCarNum = CAR_NUMBER_REGEX.search(msg[1])
            msgDate = time.time() * 1000
            if hasCarNum:
                msgs.append([msgDate / 1000, "Race Control", msg[1].upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([msgDate / 1000, "Race Control", msg[1].upper(), "raceControl"])

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

        if sector_time < 0:
            sector_time = '*'
        return (sector_time, flag)
    elif sector in previous_sectors:
        prev_sector_time = previous_sectors[sector]['SectorTime']

        if prev_sector_time < 0:
            prev_sector_time = '*'

        return (prev_sector_time, 'old')
    else:
        return ('', '')


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="HH host", default='live-api.hhtiming.com')
    parser.add_argument("--port", help="HH port", type=int, default=24688)

    a, _ = parser.parse_known_args(extra_args)
    return a


def calculate_practice_gap(first, second):
    if first and second and first.get('BestLaptime', 0) > 0 and second.get('BestLaptime', 0) > 0:
        return second['BestLaptime'] - first['BestLaptime']
    return ''


def calculate_race_gap(first, second):
    if not first or not second:
        return ''
    laps_gap = first.get('NumberOfLaps', 0) - second.get('NumberOfLaps', 0)

    first_sectors = first.get('current_sectors', {})
    first_prev = first.get('previous_sectors', {})

    second_sectors = second.get('current_sectors', {})
    second_prev = second.get('previous_sectors', {})

    if laps_gap > 1:
        return "{} laps".format(laps_gap)
    elif laps_gap == 1:
        if len(first_sectors) > len(second_sectors):
            return pluralize(laps_gap, 'lap')
        if len(second_sectors) == 0 and len(second_prev) > 0 and len(first_prev) > 0:
            max_prev = max(second_prev.keys())
            return second_prev[max_prev].get('TimelineCrossingTimeOfDay', 0) - first_prev[max_prev].get('TimelineCrossingTimeOfDay', 0)
        elif len(second_sectors) > 0:
            max_curr = max(second_sectors.keys())
            return second_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0) - first_prev[max_curr].get('TimelineCrossingTimeOfDay', 0)
        else:
            return '1 lap'
    else:
        max_curr = max(second_sectors.keys())
        if max_curr in first_sectors:
            return second_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0) - first_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0)

    return ''


def pluralize(num, singular):
    return "{} {}{}".format(
        num,
        singular,
        "s" if num != 1 else ''
    )


def sort_car_in_race(args):
    num, car = args
    current_sectors = car.get('current_sectors', {})
    latest_sector_idx = max(current_sectors.keys()) if len(current_sectors) > 0 else None
    latest_sector = current_sectors[latest_sector_idx] if latest_sector_idx else None
    latest_sector_crossing_time = latest_sector.get('TimelineCrossingTimeOfDay', 0) if latest_sector else None

    return [
        -car.get('NumberOfLaps', 0),  # Highest first
        -len(current_sectors),  # Highest first
        latest_sector_crossing_time,  # Earliest (lowest) first
        maybe_int(num)  # Doesn't really matter
    ]


def maybe_int(mi):
    try:
        return int(mi)
    except ValueError:
        return mi


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

    def notify_update(self, msg_type):
        self._last_update = time.time()
        self._due_publish_state = True

        with open(self._state_dump_file(), 'w') as outfile:
            simplejson.dump(
                self.protocol.dump_data(),
                outfile,
                sort_keys=True,
                indent='  '
            )

        if msg_type in [
            'HTiming.Core.Definitions.Communication.Messages.AdvTrackInformationMessage',
            'HTiming.Core.Definitions.Communication.Messages.EventMessage',
            'HTiming.Core.Definitions.Communication.Messages.SessionInfoMessage'
        ]:
            # Any of those messages could change data encoded in our manifest
            self.publishManifest()

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
        pre_sectors = [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.TEAM,
            Stat.DRIVER,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT
        ]

        sectors = []
        for sector in self._sectors_list():
            sectors.append(Stat.sector(sector['SectorName'][1:]))
            sectors.append(Stat.best_sector(sector['SectorName'][1:]))

        post_sectors = [
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

        return pre_sectors + sectors + post_sectors

    def _sectors_list(self):
        return self.protocol.track.get('OrderedListOfOnTrackSectors', {}).get('$values', [])

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
            return lambda (num, car): (car.get('BestLaptime', 999999), maybe_int(num))
        else:
            return sort_car_in_race

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
            for s in self._sectors_list():
                sector = s['StartTimeLine']
                best_sector = car.get('PersonalBestSectors', {}).get(sector, None)
                existing_best_sector = best_by_class[clazz].get(sector, None)
                if best_sector and best_sector > 0 and (not existing_best_sector or existing_best_sector[0] > best_sector):
                    best_by_class[clazz][sector] = (best_sector, num)

        gap_func = self._gap_function()

        sorted_cars = sorted(self.protocol.cars.iteritems(), key=self._car_sort_function())

        for num, car in sorted_cars:
            if car.get('CompetitorID', False):  # Exclude course cars etc.
                driver = car.get('driver', {})
                clazz = car.get('CategoryID')

                leader = sorted_cars[0][1] if len(sorted_cars) > 0 and len(cars) > 0 else None
                prev_car = sorted_cars[len(cars) - 1][1] if len(cars) > 0 else None

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

                bbc = best_by_class[clazz]

                for s in self._sectors_list():
                    sector = s['StartTimeLine']
                    car_data.append(
                        _extract_sector(
                            sector,
                            car,
                            num,
                            bbc
                        )
                    )

                    best_sec_time = car.get('PersonalBestSectors', {}).get(sector, '')
                    if best_sec_time < 0:
                        best_sec_time = '*'

                    car_data.append(
                        (best_sec_time, 'sb' if sector in bbc and bbc[sector][1] == num else 'old')
                    )

                last_lap = car.get('LapTime', '')
                best_lap = car.get('BestLaptime', '')
                best_lap_in_class = best_by_class[clazz].get(0)

                if best_lap_in_class and num == best_lap_in_class[1]:
                    best_lap_flag = 'sb-new' if last_lap == best_lap and car_data[-2][0] != '' and car_data[-2][1] != 'old' else 'sb'
                else:
                    best_lap_flag = ''

                car_data += [
                    (last_lap, 'pb' if last_lap == best_lap and best_lap != '' else ''),
                    (best_lap, best_lap_flag),
                    car.get('Pits', '')
                ]

                cars.append(car_data)
        return cars

    def _map_session(self):
        hhs = self.protocol.session
        delta = time.time() - hhs['LastUpdate']
        session = {
            'flagState': FLAG_STATE_MAP.get(hhs.get('TrackStatus', 0), FlagStatus.NONE).name.lower(),
            'timeElapsed': hhs.get('SessionTime', 0) + delta
        }

        if hhs.get('TimeToGo'):
            session['timeRemain'] = hhs['TimeToGo']

        return session
