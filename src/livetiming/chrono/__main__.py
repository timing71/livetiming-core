from livetiming.chrono import alkamel
from livetiming.racing import Stat
from livetiming.dvr import DirectoryTimingRecorder

import argparse
import sys
import uuid

_FORMATS = {
    'alkamel': alkamel
}


def _parse_args():
    parser = argparse.ArgumentParser(description='Tool for creating Live Timing recordings from chronological analysis files.')

    subparsers = parser.add_subparsers(help='Format-specific help')

    for format_name, format_module in _FORMATS.iteritems():
        subparser = subparsers.add_parser(format_name)
        if hasattr(format_module, 'generate_parser_args') and callable(getattr(format_module, 'generate_parser_args')):
            format_module.generate_parser_args(subparser)
        subparser.set_defaults(create_events=format_module.create_events)
        subparser.set_defaults(create_initial_state=format_module.create_initial_state)
        subparser.set_defaults(message_generators=format_module.message_generators)
        subparser.set_defaults(sort_cars=format_module.sort_cars)
        subparser.set_defaults(get_start_time=format_module.get_start_time)
        subparser.set_defaults(colspec=format_module.COLSPEC)

    parser.add_argument('--output', '-o', help='Output filename (\'.zip\' will be appended)', default='output')

    return parser.parse_args()


def main():
    args = _parse_args()
    initial_state = args.create_initial_state(args, [0, 0, 0, 0, 0])

    events = sorted(args.create_events(args), key=lambda e: e.timestamp)
    evt_count = len(events)

    print "Generated {} events".format(evt_count)

    message_generators = args.message_generators()

    car_state = initial_state
    state = {
        'cars': args.sort_cars(args, car_state.values()),
        'session': {'timeElapsed': 0},
        'messages': []
    }

    recorder = DirectoryTimingRecorder(args.output)
    my_uuid = uuid.uuid4().hex
    recorder.writeManifest({
        'description': 'Converted chrono dump',
        'name': 'converted',
        'uuid': my_uuid,
        'colSpec': map(lambda s: s.value if isinstance(s, Stat) else s, args.colspec)
    })
    next_frame_threshold = 0

    session_start_time = args.get_start_time(args)
    recorder.writeState(state, session_start_time)

    for idx, evt in enumerate(events):
        sys.stdout.write(
            "\rProcessing event {} / {} {}%".format(
                idx + 1,
                evt_count,
                100 * (idx + 1) / evt_count
            )
        )
        sys.stdout.flush()

        evt_time = evt.timestamp
        car_state = evt(car_state)

        elapsed = evt_time - session_start_time

        new_state = {
            'cars': args.sort_cars(args, car_state.values()),
            'session': {
                'timeElapsed': elapsed,
                'timeRemain': int(args.duration) - elapsed
            },
            'messages': state['messages']
        }

        new_state['messages'] = _generate_messages(message_generators, evt_time, state, new_state)

        if evt_time > next_frame_threshold:
            calculate_gap_and_int(args.colspec, new_state)
            recorder.writeState(new_state, int(evt_time))
            next_frame_threshold = evt_time + 1

        state = new_state

    print ''
    recorder.writeState(state, int(events[-1].timestamp))
    of = recorder.finalise()
    print "Created {} (UUID {})".format(of, my_uuid)


def if_positive(val, otherwise=''):
    if val >= 0:
        return val
    return otherwise


def calculate_gap_and_int(colspec, state):
    gap_idx = colspec.index(Stat.GAP)
    int_idx = colspec.index(Stat.INT)
    laps_idx = colspec.index(Stat.LAPS)

    if laps_idx and (gap_idx or int_idx):
        cars = state['cars']
        if len(cars) > 1:
            leader = cars[0]
            for pos_minus_one, car in enumerate(cars):
                pos = pos_minus_one + 1
                if pos > 1:
                    prev_car = cars[pos_minus_one - 1]
                    if gap_idx:
                        car[gap_idx] = if_positive(_gap_between(leader, leader[laps_idx], car, car[laps_idx]))
                    if int_idx:
                        car[int_idx] = if_positive(_gap_between(prev_car, prev_car[laps_idx], car, car[laps_idx]))
                else:
                    if gap_idx:
                        car[gap_idx] = ''
                    if int_idx:
                        car[int_idx] = ''


def _gap_between(first, first_laps, second, second_laps):
    laps_diff = first_laps - second_laps

    if laps_diff > 1:
        return '{} laps'.format(laps_diff)
    else:
        first_passing = first[-1]
        second_passing = second[-1]

        first_cur_sector = first_passing[-1]
        second_cur_sector = second_passing[-1]

        if laps_diff == 0 or first_cur_sector < second_cur_sector:
            return second_passing[second_cur_sector] - first_passing[second_cur_sector]
        else:
            return '1 lap'

    return ''


def _generate_messages(generators, timestamp, old_state, new_state):
    new_messages = []

    for generator in generators:
        new_messages += generator.process(old_state, new_state)

    # Fix up message timestamps
    new_messages = map(lambda m: [timestamp] + m[1:], new_messages)

    return (new_messages + old_state['messages'])[0:100]


main()
