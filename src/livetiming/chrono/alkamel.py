from datetime import datetime, timedelta
from livetiming.chrono import DriverChangeEvent, LaptimeEvent, PitInEvent, PitOutEvent, SectorEvent
from livetiming.messages import CarPitMessage, DriverChangeMessage, FastLapMessage
from livetiming.racing import Stat

import calendar
import csv
import re


COLSPEC = [
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


def parseTime(formattedTime):
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
                try:
                    ttime = datetime.strptime(formattedTime, "%M'%S.%f")
                    return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
                except Exception:
                    return formattedTime


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


def _parse_clock_with_elapsed(start_date, hour, elapsed):
    elapsed_time = _parse_clock_time(elapsed)
    hour_num = int(hour[0:2])

    delta = timedelta(hours=hour_num, minutes=elapsed_time.minute, seconds=elapsed_time.second, microseconds=elapsed_time.microsecond)
    return start_date + delta


def _parse_clock_from_elapsed(start_time, elapsed):

    add_day = False
    if len(elapsed) > 9 and elapsed.startswith('24:'):
        add_day = True
        elapsed = elapsed[3:]

    elapsed_time = _parse_clock_time(elapsed)

    delta = timedelta(
        days=1 if add_day else 0,
        hours=elapsed_time.hour,
        minutes=elapsed_time.minute,
        seconds=elapsed_time.second,
        microseconds=elapsed_time.microsecond
    )

    munged = start_time + delta
    print(munged)
    return munged


def generate_parser_args(parser):
    parser.add_argument('--chronological-analysis', '-c', help='Chronological analysis CSV file', required=True)
    parser.add_argument('--start-date', '-s', help='Date at start of session', required=True)
    parser.add_argument('--duration', '-d', help='Duration (in seconds) of session', required=True)


def create_events(args):
    events = []

    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    start_time = get_start_time(args, False)

    with open(args.chronological_analysis, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        prev_row = None
        prev_race_num = None
        for row in reader:
            race_num = row['\ufeffNUMBER']

            clock_time = _parse_clock_time(row[' HOUR'])

            if clock_time:
                ts = start_date.replace(
                    hour=clock_time.hour,
                    minute=clock_time.minute,
                    second=clock_time.second,
                    microsecond=clock_time.microsecond
                )
                datestamp = float(calendar.timegm(ts.timetuple())) + (clock_time.microsecond / 1000000.0)
            else:
                ts = _parse_clock_from_elapsed(start_time, row[' ELAPSED'])
                datestamp = float(calendar.timegm(ts.timetuple())) + (ts.microsecond / 1000000.0)

            lap_time = parseTime(row[' LAP_TIME'])
            time_in_pit = parseTime(row['PIT_TIME'])

            if not prev_row or prev_row[' CROSSING_FINISH_LINE_IN_PIT'] == 'B':
                events.append(PitOutEvent(datestamp - lap_time + time_in_pit, COLSPEC, race_num))
            if not prev_row or prev_row['DRIVER_NAME'] != row['DRIVER_NAME']:
                events.append(DriverChangeEvent(datestamp - lap_time + time_in_pit - 1, COLSPEC, race_num, row['DRIVER_NAME']))

            s1_time = parseTime(row[' S1'])
            s2_time = parseTime(row[' S2'])
            s3_time = parseTime(row[' S3'])

            events.append(
                SectorEvent(datestamp - s2_time - s3_time, COLSPEC, race_num, 1, s1_time, _parseFlags(row[' S1_IMPROVEMENT']))
            )
            events.append(
                SectorEvent(datestamp - s3_time, COLSPEC, race_num, 2, s2_time, _parseFlags(row[' S2_IMPROVEMENT']))
            )
            events.append(
                SectorEvent(datestamp, COLSPEC, race_num, 3, s3_time, _parseFlags(row[' S3_IMPROVEMENT']))
            )

            if row[' CROSSING_FINISH_LINE_IN_PIT'] == 'B':
                events.append(PitInEvent(datestamp, COLSPEC, race_num))
            else:
                events.append(
                    LaptimeEvent(datestamp, COLSPEC, race_num, lap_time, _parseFlags(row[' LAP_IMPROVEMENT']))
                )

            if not prev_race_num or prev_race_num == race_num:
                prev_row = row
            else:
                prev_row = None
    return events


def create_initial_state(args, extra):
    state = {}
    with open(args.chronological_analysis, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        for row in reader:
            race_num = row['\ufeffNUMBER']
            if race_num not in state:
                state[race_num] = [
                    race_num,
                    'N/S',
                    row.get('CLASS', ''),
                    row['DRIVER_NAME'],
                    row.get('TEAM', ''),
                    0,
                    '',
                    '',
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    ['', ''],
                    None,
                    extra
                ]

    return state


def get_start_time(args, as_timestamp=True):
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    with open(args.chronological_analysis, 'r') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        row = next(reader)

        clock_time = _parse_clock_time(row[' HOUR'])
        if clock_time:
            ts = start_date.replace(hour=clock_time.hour, minute=clock_time.minute, second=clock_time.second)
        else:
            ts = _parse_clock_with_elapsed(start_date, row[' HOUR'], row[' ELAPSED'])

        elapsed_raw = row[' ELAPSED']
        elapsed = re.match(r"((?P<hours>[0-9]+):)?(?P<minutes>[0-9]+):(?P<seconds>[0-9]+\.[0-9]+)", elapsed_raw)
        delta = timedelta(
            hours=int(elapsed.group('hours') or 0),
            minutes=int(elapsed.group('minutes')),
            milliseconds=float(elapsed.group('seconds')) * 1000
        )

        if as_timestamp:
            return calendar.timegm((ts - delta).timetuple()) + 1
        else:
            return ts - delta


def get_duration(args):
    return args.duration


def _car_sort_idx(c):
    last_passing = c[-1]
    try:
        race_num_as_int = int(c[0])
    except ValueError:
        race_num_as_int = c[0]

    return [
        -c[5],  # laps completed
        -last_passing[-1],  # current sector
        last_passing[last_passing[-1]],  # time of arrival at current sector
        race_num_as_int,
    ]


def sort_cars(args, cars):
    # return sorted(cars, key=lambda c: (c[15] if c[15] > 0 else 99999999, c[0]))
    return sorted(cars, key=_car_sort_idx, reverse=False)


def message_generators():
    return [
        FastLapMessage(COLSPEC),
        CarPitMessage(COLSPEC),
        DriverChangeMessage(COLSPEC)
    ]
