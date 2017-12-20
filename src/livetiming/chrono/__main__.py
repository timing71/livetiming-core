import argparse

from livetiming.chrono import alkamel

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

    return parser.parse_args()


def main():
    args = _parse_args()
    initial_state = args.create_initial_state(args)

    events = sorted(args.create_events(args), key=lambda e: e[0])

    message_generators = args.message_generators()

    car_state = initial_state
    state = {
        'cars': args.sort_cars(args, car_state.values()),
        'session': {},
        'messages': []
    }
    for evt_time, evt in events:
        car_state = evt(car_state)
        new_state = {
            'cars': args.sort_cars(args, car_state.values()),
            'session': state['session'],
            'messages': state['messages']
        }

        new_state['messages'] = _generate_messages(message_generators, evt_time, state, new_state)

        print "{} State now {}".format(evt_time, new_state)
        state = new_state


def _generate_messages(generators, timestamp, old_state, new_state):
    new_messages = []

    for generator in generators:
        new_messages += generator.process(old_state, new_state)

    # Fix up message timestamps
    new_messages = map(lambda m: [timestamp] + m[1:], new_messages)

    return (new_messages + old_state['messages'])[0:100]


main()
