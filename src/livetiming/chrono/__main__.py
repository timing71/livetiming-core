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

    return parser.parse_args()


def main():
    args = _parse_args()
    initial_state = args.create_initial_state(args)
    print initial_state
    events = sorted(args.create_events(args), key=lambda e: e[0])
    print events

    state = initial_state
    for evt_time, evt in events:
        evt(state)

    print state


main()
