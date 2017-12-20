from datetime import datetime
from livetiming.chrono import LaptimeEvent, SectorEvent
from livetiming.messages import FastLapMessage
from livetiming.racing import Stat
from livetiming.service.wec import parseTime

import calendar
import csv


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
        return None


def generate_parser_args(parser):
    parser.add_argument('--chronological-analysis', '-c', help='Chronological analysis CSV file', required=True)
    parser.add_argument('--start-date', '-s', help='Date at start of session', required=True)


def create_events(args):
    events = []

    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    with open(args.chronological_analysis, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        for row in reader:
            race_num = row['\xef\xbb\xbfNUMBER']
            clock_time = _parse_clock_time(row[' HOUR'])

            ts = start_date.replace(hour=clock_time.hour, minute=clock_time.minute, second=clock_time.second)
            datestamp = calendar.timegm(ts.timetuple())

            events.append(
                (datestamp, SectorEvent(_COLSPEC, race_num, 3, parseTime(row[' S3']), _parseFlags(row[' S3_IMPROVEMENT'])))
            )
            events.append(
                (datestamp, LaptimeEvent(_COLSPEC, race_num, parseTime(row[' LAP_TIME']), _parseFlags(row[' LAP_IMPROVEMENT'])))
            )
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
                    'RUN',
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


def sort_cars(args, cars):
    return sorted(cars, key=lambda c: c[15])


def message_generators():
    return [
        FastLapMessage(_COLSPEC)
    ]
