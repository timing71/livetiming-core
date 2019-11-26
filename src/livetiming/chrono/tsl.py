from datetime import datetime, timedelta
from livetiming.chrono import DriverChangeEvent, FlagEvent, LaptimeEvent, PitInEvent, PitOutEvent
from livetiming.messages import CarPitMessage, DriverChangeMessage, FastLapMessage, FlagChangeMessage
from livetiming.racing import Stat, FlagStatus

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
    Stat.LAST_LAP,
    Stat.BEST_LAP,
    Stat.PITS
]


def _parse_clock_time(clock):
    try:
        return datetime.strptime(clock, "%H:%M:%S.%f").time()
    except ValueError:
        try:
            return datetime.strptime(clock, "%M:%S.%f").time()
        except ValueError:
            return None


def _parse_time(formattedTime):
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
                except ValueError:
                    return formattedTime


def generate_parser_args(parser):
    parser.add_argument('--input', '-i', help='Input CSV file', required=True)
    parser.add_argument('--start-date', '-s', help='Date at start of session', required=True)
    parser.add_argument('--flags', help='CSV file with flag state changes')


def get_start_time(args):
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    with open(args.input, 'r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        next(reader)  # skip inexplicable blank line
        row = next(reader)

        clock_time = _parse_clock_time(row['time_of_day'])

        ts = start_date.replace(hour=clock_time.hour, minute=clock_time.minute, second=clock_time.second)

        elapsed_raw = row['session_time']
        elapsed = re.match("((?P<hours>[0-9]+):)?(?P<minutes>[0-9]+):(?P<seconds>[0-9]+\.[0-9]+)", elapsed_raw)
        delta = timedelta(
            hours=int(elapsed.group('hours') or 0),
            minutes=int(elapsed.group('minutes')),
            milliseconds=float(elapsed.group('seconds')) * 1000
        )

        return calendar.timegm((ts - delta).timetuple()) + 1


def get_duration(args):
    return 0


def create_initial_state(args, extras):
    state = {
        'cars': {},
        'session': {
            'flagState': 'none'
        }
    }
    with open(args.input, 'r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')
        for row in reader:
            race_num = row['nr']
            if race_num not in state['cars']:
                state['cars'][race_num] = [
                    race_num,
                    'N/S',
                    row['class'],
                    row['driver_name'],
                    row['driver_or_team'],
                    0,
                    '',
                    '',
                    ['', ''],
                    ['', ''],
                    None,
                    extras
                ]

    return state


def create_events(args):
    events = []
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    def make_datestamp(clock_time):
        ts = start_date + timedelta(
            hours=clock_time.hour,
            minutes=clock_time.minute,
            seconds=clock_time.second,
            microseconds=clock_time.microsecond
        )
        return float(calendar.timegm(ts.timetuple())) + (clock_time.microsecond / 1000000.0)

    with open(args.input, 'r', newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',')

        prev_row = None
        prev_race_num = None

        for row in reader:
            race_num = row['nr']
            clock_time = _parse_clock_time(row['time_of_day'])

            lap_time = _parse_time(row['laptime'])

            events.append(
                LaptimeEvent(
                    make_datestamp(clock_time),
                    COLSPEC,
                    race_num,
                    lap_time,
                    ''
                )
            )

            if row['in_lap']:
                events.append(
                    PitInEvent(
                        make_datestamp(_parse_clock_time(row['time_in_lap'])),
                        COLSPEC,
                        race_num
                    )
                )

            if row['out_lap']:
                out_time = make_datestamp(_parse_clock_time(row['time_out_lap']))
                events.append(
                    PitOutEvent(
                        out_time,
                        COLSPEC,
                        race_num
                    )
                )

                if prev_race_num == race_num:
                    old_driver = prev_row['driver_name']
                    new_driver = row['driver_name']
                    if new_driver != old_driver:
                        events.append(
                            DriverChangeEvent(
                                out_time - 1,
                                COLSPEC,
                                race_num,
                                new_driver
                            )
                        )

            prev_race_num = race_num
            prev_row = row

    if args.flags:
        with open(args.flags, 'r', newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=',')
            for row in reader:
                events.append(
                    FlagEvent(
                        make_datestamp(_parse_clock_time(row['TIME OF DAY'])),
                        _FLAG_MAP.get(row['TYPE'], FlagStatus.NONE).name.lower()
                    )
                )

    return events


_FLAG_MAP = {
    'GREEN': FlagStatus.GREEN,
    'SAFETY': FlagStatus.SC,
    'FINISH': FlagStatus.CHEQUERED
}


def sort_cars(args, cars):
    return sorted(
        cars,
        key=lambda c: [c[5], c[-1][0]],
        reverse=True
    )


def message_generators():
    return [
        FastLapMessage(COLSPEC),
        CarPitMessage(COLSPEC),
        DriverChangeMessage(COLSPEC),
        FlagChangeMessage()
    ]
