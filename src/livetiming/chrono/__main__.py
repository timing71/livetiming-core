import argparse

from livetiming.chrono import alkamel
from livetiming.racing import Stat
from livetiming.recording import TimingRecorder
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

    parser.add_argument('--output', '-o', help='Output filename', default='output.zip')

    return parser.parse_args()


def main():
    args = _parse_args()
    initial_state = args.create_initial_state(args, [None, None, None, None, 0])

    events = sorted(args.create_events(args), key=lambda e: e.timestamp)

    message_generators = args.message_generators()

    car_state = initial_state
    state = {
        'cars': args.sort_cars(args, car_state.values()),
        'session': {'timeElapsed': 0},
        'messages': []
    }

    recorder = TimingRecorder(args.output)
    recorder.writeManifest({
        'description': 'Converted chrono dump',
        'name': 'converted',
        'uuid': uuid.uuid4().hex,
        'colSpec': map(lambda s: s.value if isinstance(s, Stat) else s, args.colspec)
    })
    next_frame_threshold = 0

    session_start_time = args.get_start_time(args)
    recorder.writeState(state, session_start_time)

    for evt in events:
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
            recorder.writeState(new_state, evt_time)
            next_frame_threshold = evt_time + 1

        state = new_state

    recorder.writeState(state, events[-1].timestamp)


def _generate_messages(generators, timestamp, old_state, new_state):
    new_messages = []

    for generator in generators:
        new_messages += generator.process(old_state, new_state)

    # Fix up message timestamps
    new_messages = map(lambda m: [timestamp] + m[1:], new_messages)

    return (new_messages + old_state['messages'])[0:100]


main()
