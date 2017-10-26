from datetime import datetime
from livetiming.chrono import LaptimeEvent, SectorEvent
from livetiming.racing import Stat
from livetiming.service.wec import parseTime

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


def create_events(args):
    events = []
    with open(args.chronological_analysis, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        for row in reader:
            race_num = row['\xef\xbb\xbfNUMBER']
            clock_time = _parse_clock_time(row[' HOUR'])

            events.append(
                (clock_time, SectorEvent(_COLSPEC, race_num, 3, parseTime(row[' S3']), _parseFlags(row[' S3_IMPROVEMENT'])))
            )
            events.append(
                (clock_time, LaptimeEvent(_COLSPEC, race_num, parseTime(row[' LAP_TIME']), _parseFlags(row[' LAP_IMPROVEMENT'])))
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
                    row['CLASS'],
                    row['DRIVER_NAME'],
                    row['TEAM'],
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
