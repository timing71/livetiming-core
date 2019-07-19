# -*- coding: utf-8 -*-
from collections import defaultdict
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service
from livetiming.service.hhtiming import create_protocol_factory, RaceControlMessage
from livetiming.service.hhtiming.types import SectorStatus
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint
from twisted.internet.task import LoopingCall

import argparse
import simplejson
import time


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
    5: FlagStatus.GREEN,
    7: FlagStatus.FCY
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

        if len(current_sectors) > 0:
            flag = 'old'
        elif best and best[1] == num and best[0] == prev_sector_time:
            flag = 'sb'
        elif sector in pb_sectors and pb_sectors[sector] == prev_sector_time:
            flag = 'pb'
        else:
            flag = ''

        if prev_sector_time < 0:
            prev_sector_time = '*'

        return (prev_sector_time, flag)
    else:
        return ('', '')


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="HH host", default='live-api.hhtiming.com')
    parser.add_argument("--port", help="HH port", type=int, default=24688)
    parser.add_argument('--time', '-t', help='Total time in session', type=int, default=None)
    parser.add_argument('--no-dump', help='Don\'t dump HH state to file', action='store_true')

    a, _ = parser.parse_known_args(extra_args)
    return a


def calculate_practice_gap(first, second):
    if first and second and 1e7 > first.get('BestLaptime', 0) > 0 and 1e7 > second.get('BestLaptime', 0) > 0:
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
            max_prev = max(second_prev.keys()) if len(second_prev) > 0 else None
            return second_prev[max_prev].get('TimelineCrossingTimeOfDay', 0) - first_prev[max_prev].get('TimelineCrossingTimeOfDay', 0)
        elif len(second_sectors) > 0:
            max_curr = max(second_sectors.keys())
            return second_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0) - first_prev.get(max_curr, {}).get('TimelineCrossingTimeOfDay', 0)
        else:
            return '1 lap'
    else:
        max_curr = max(second_sectors.keys()) if len(second_sectors) > 0 else None
        if max_curr and max_curr in first_sectors:
            return second_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0) - first_sectors[max_curr].get('TimelineCrossingTimeOfDay', 0)
        if len(second_prev) > 0:
            max_prev = max(second_prev.keys())
            return second_prev[max_prev].get('TimelineCrossingTimeOfDay', 0) - first_prev[max_prev].get('TimelineCrossingTimeOfDay', 0)

        second_elapsed = second.get('LastElapsedTime', 0)
        first_elapsed = first.get('LastElapsedTime', 0)
        if first_elapsed > 0 and second_elapsed > 0:
            return second_elapsed - first_elapsed

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

    prev_sectors = car.get('previous_sectors', {})
    prev_sector_idx = max(prev_sectors.keys()) if len(prev_sectors) > 0 else None
    prev_sector = prev_sectors[prev_sector_idx] if prev_sector_idx else None

    if latest_sector:
        latest_sector_crossing_time = latest_sector.get('TimelineCrossingTimeOfDay', 0)
    elif prev_sector:
        latest_sector_crossing_time = prev_sector.get('TimelineCrossingTimeOfDay', 0)
    else:
        latest_sector_crossing_time = None

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
        self._protocol_factory = create_protocol_factory(self, self._state_dump_file())
        self.protocol = None
        self._extra_args = parse_extra_args(extra_args)

        self._rcMessageGenerator = RaceControlMessage(None)

        self._due_publish_state = False
        self._last_update = time.time()

        self._has_weather = False

    def _state_dump_file(self):
        return 'hhtiming_state_dump_{}.json'.format(self.uuid)

    def set_protocol(self, protocol):
        self.protocol = protocol
        self._rcMessageGenerator.protocol = protocol

    def notify_update(self, msg_type, data):
        self._last_update = time.time()
        self._due_publish_state = True

        if not self._extra_args.no_dump and self.protocol:
            with open(self._state_dump_file(), 'w') as outfile:
                simplejson.dump(
                    self.protocol.dump_data(),
                    outfile,
                    sort_keys=True,
                    indent='  '
                )

        if msg_type == 'HTiming.Core.Definitions.Communication.Messages.WeatherTSMessage' and not self._has_weather:
            self._has_weather = True
            self.publishManifest()
        elif msg_type in [
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

        reactor.connectTCP(
            self._extra_args.host,
            self._extra_args.port,
            self._protocol_factory
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
        if self.protocol:
            return self.protocol.track.get('OrderedListOfOnTrackSectors', {}).get('$values', [])
        return []

    def getName(self):
        if self.protocol:
            return self.protocol.session.get('EventName', 'Live Timing')
        return 'Live Timing'

    def getDefaultDescription(self):
        if self.protocol:
            return self.protocol.session.get('SessionDescription', '')
        return ''

    def getRaceState(self):
        return {
            'cars': self._map_cars(),
            'session': self._map_session()
        }

    def getTrackDataSpec(self):
        if self._has_weather:
            return [
                "Air Temp",
                "Humidity",
                "Wind Speed",
                "Wind Direction"
            ]
        return []

    def getExtraMessageGenerators(self):
        return [
            self._rcMessageGenerator
        ]

    def _car_sort_function(self):
        if self.protocol.session.get('SessionType') < 3 and self.protocol.session.get('SessionType') > 0:
            return lambda num_car: (num_car[1].get('BestLaptime', 999999), maybe_int(num_car[0]))
        else:
            return sort_car_in_race

    def _gap_function(self):
        if self.protocol.session.get('SessionType') < 3 and self.protocol.session.get('SessionType') > 0:
            return calculate_practice_gap
        else:
            return calculate_race_gap

    def _map_cars(self):
        if not self.protocol:
            return []

        cars = []

        best_by_class = defaultdict(dict)

        for num, car in self.protocol.cars.items():
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

        sorted_cars = sorted(iter(self.protocol.cars.items()), key=self._car_sort_function())

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
                    "{} {}".format(driver.get('FirstName', ''), driver.get('LastName', '')).strip(),
                    car.get('CarMake'),
                    car.get('NumberOfLaps'),
                    gap_func(leader, car),
                    gap_func(prev_car, car)
                ]

                bbc = best_by_class[clazz]

                last_sector_idx = None
                for s in self._sectors_list():
                    sector = s['EndTimeLine']
                    car_data.append(
                        _extract_sector(
                            sector,
                            car,
                            num,
                            bbc
                        )
                    )
                    last_sector_idx = str(sector)

                    best_sec_time = car.get('PersonalBestSectors', {}).get(sector, '')
                    try:
                        if best_sec_time < 0:
                            best_sec_time = '*'
                    except TypeError:
                        pass

                    car_data.append(
                        (best_sec_time, 'sb' if sector in bbc and bbc[sector][1] == num else 'old')
                    )

                last_lap = car.get('LapTime', '')
                best_lap = car.get('BestLaptime', '')
                best_lap_in_class = best_by_class[clazz].get(0)

                if best_lap_in_class and num == best_lap_in_class[1]:
                    best_lap_flag = 'sb'
                else:
                    best_lap_flag = ''

                if last_lap == best_lap and best_lap != '':
                    if best_lap_flag == 'sb':
                        last_sector = car_data[last_sector_idx] if last_sector_idx else None
                        if not last_sector or (last_sector[0] != '' and last_sector[1] != 'old' and last_sector_idx in car.get('current_sectors', {})):
                            last_lap_flag = 'sb-new'
                        else:
                            last_lap_flag = 'sb'
                    else:
                        last_lap_flag = 'pb'
                else:
                    last_lap_flag = ''

                car_data += [
                    (last_lap, last_lap_flag),
                    (best_lap if best_lap and best_lap < 1e7 else '', best_lap_flag),
                    car.get('Pits', '')
                ]

                cars.append(car_data)
        return cars

    def _map_session(self):
        if not self.protocol:
            return {
                'flagState': 'none',
                'timeElapsed': 0
            }
        hhs = self.protocol.session
        weather = self.protocol.weather
        delta = time.time() - hhs['LastUpdate'] if 'LastUpdate' in hhs else 0
        session = {
            'flagState': self._map_session_flag(),
            'timeElapsed': hhs.get('SessionTime', 0) + delta,
            'trackData': [
                "{}°C".format(round(weather['AirTemperature'], 1)) if 'AirTemperature' in weather else '-',
                "{}%".format(int(weather['Humidity'])) if 'Humidity' in weather else '-',
                "{} m/s".format(round(weather['WindSpeed'], 1)) if 'WindSpeed' in weather else '-',
                "{}°".format(round(weather['WindDirection'], 1)) if 'WindDirection' in weather else '-'
            ]
        }

        if hhs.get('TimeToGo'):
            session['timeRemain'] = hhs['TimeToGo']
        elif self._extra_args.time:
            session['timeRemain'] = max(0, self._extra_args.time - hhs.get('SessionTime', 0) - delta)

        return session

    def _map_session_flag(self):
        zone_states = [s.get('ZoneStatus', 0) for s in list(self.protocol.sector_states.values())]
        if SectorStatus.SLOW_ZONE in zone_states:
            return FlagStatus.SLOW_ZONE.name.lower()
        hhs = self.protocol.session
        return FLAG_STATE_MAP.get(hhs.get('TrackStatus', 0), FlagStatus.NONE).name.lower()
