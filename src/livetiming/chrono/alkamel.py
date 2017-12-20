from datetime import datetime, timedelta
from livetiming.chrono import LaptimeEvent, PitInEvent, PitOutEvent, SectorEvent
from livetiming.messages import FastLapMessage, CarPitMessage
from livetiming.racing import Stat
from livetiming.service.wec import parseTime

import calendar
import csv
import re


_COLSPEC = [
    Stat.NUM,
    Stat.STATE,
    Stat.CLASS,
    Stat.DRIVER,
    Stat.TEAM,
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


def _parseFlags(flag):
    _flags = {
        0: '',
        1: 'pb',
        2: 'sb'
    }
    if flag in _flags:
        return _flags[flag]
    return ''


def _parse_clock_time(clock):
    try:
        return datetime.strptime(clock, "%H:%M:%S.%f").time()
    except ValueError:
        try:
            return datetime.strptime(clock, "%M:%S.%f").time()
        except ValueError:
            return None


def generate_parser_args(parser):
    parser.add_argument('--chronological-analysis', '-c', help='Chronological analysis CSV file', required=True)
    parser.add_argument('--start-date', '-s', help='Date at start of session', required=True)


def create_events(args):
    events = []

    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    with open(args.chronological_analysis, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        prev_row = None
        prev_race_num = None
        for row in reader:
            race_num = row['\xef\xbb\xbfNUMBER']
            clock_time = _parse_clock_time(row[' HOUR'])

            ts = start_date.replace(hour=clock_time.hour, minute=clock_time.minute, second=clock_time.second)
            datestamp = calendar.timegm(ts.timetuple())

            lap_time = parseTime(row[' LAP_TIME'])
            time_in_pit = parseTime(row['PIT_TIME'])

            if not prev_row or prev_row[' CROSSING_FINISH_LINE_IN_PIT'] == 'B':
                events.append((int(datestamp - lap_time + time_in_pit), PitOutEvent(_COLSPEC, race_num)))

            s1_time = parseTime(row[' S1'])
            s2_time = parseTime(row[' S2'])
            s3_time = parseTime(row[' S3'])

            events.append(
                (int(datestamp - s2_time - s3_time), SectorEvent(_COLSPEC, race_num, 1, s1_time, _parseFlags(row[' S1_IMPROVEMENT'])))
            )
            events.append(
                (int(datestamp - s3_time), SectorEvent(_COLSPEC, race_num, 2, s2_time, _parseFlags(row[' S2_IMPROVEMENT'])))
            )
            events.append(
                (datestamp, SectorEvent(_COLSPEC, race_num, 3, s3_time, _parseFlags(row[' S3_IMPROVEMENT'])))
            )

            if row[' CROSSING_FINISH_LINE_IN_PIT'] == 'B':
                events.append((datestamp, PitInEvent(_COLSPEC, race_num)))
            else:
                events.append(
                    (datestamp, LaptimeEvent(_COLSPEC, race_num, lap_time, _parseFlags(row[' LAP_IMPROVEMENT'])))
                )

            if prev_race_num == race_num:
                prev_row = row
            else:
                prev_row = None
    return events


def create_initial_state(args):
    state = {}
    with open(args.chronological_analysis, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        for row in reader:
            race_num = row['\xef\xbb\xbfNUMBER']
            if race_num not in state:
                state[race_num] = [
                    race_num,
                    'PIT',
                    row['CLASS'].decode('utf-8'),
                    row['DRIVER_NAME'].decode('utf-8'),
                    row['TEAM'].decode('utf-8'),
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None
                ]

    return state


def get_start_time(args):
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    with open(args.chronological_analysis, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        row = reader.next()

        clock_time = _parse_clock_time(row[' HOUR'])

        ts = start_date.replace(hour=clock_time.hour, minute=clock_time.minute, second=clock_time.second)

        elapsed_raw = row[' ELAPSED']
        elapsed = re.match("((?P<hours>[0-9]+):)?(?P<minutes>[0-9]+):(?P<seconds>[0-9]+\.[0-9]+)", elapsed_raw)
        delta = timedelta(hours=int(elapsed.group('hours') or 0), minutes=int(elapsed.group('minutes')), seconds=float(elapsed.group('seconds')))

        return calendar.timegm((ts - delta).timetuple()) + 1


def sort_cars(args, cars):
    return sorted(cars, key=lambda c: (c[15] if c[15] > 0 else 99999999, c[0]))


def message_generators():
    return [
        FastLapMessage(_COLSPEC),
        CarPitMessage(_COLSPEC)
    ]
