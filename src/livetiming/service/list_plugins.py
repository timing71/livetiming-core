from livetiming.service import get_plugin_source

import argparse
import simplejson


BOLD = '\033[1m'
END = '\033[0m'


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-H',
        '--human-readable',
        action='store_true',
        help='Give human-readable output (default is to output JSON)'
    )

    args = parser.parse_args()

    with get_plugin_source() as source:
        plugins = list(
            filter(
                lambda p: p[0] != '_',
                source.list_plugins()
            )
        )

        plugin_stats = {
            p: getattr(source.load_plugin(p), '__spec', {}) for p in plugins
        }

        if args.human_readable:
            if plugin_stats:
                print('Available plugins:')
                for name, plugin in plugin_stats.items():
                    print('{}{}{}'.format(
                        BOLD,
                        name,
                        END
                    ))
                    if 'description' in plugin:
                        print('\t{}'.format(plugin['description']))
            else:
                print('No plugins available')
        else:
            print(simplejson.dumps(plugin_stats))


if __name__ == '__main__':
    main()
