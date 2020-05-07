from livetiming.service import get_plugin_source

import simplejson


def main():
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

        print(simplejson.dumps(plugin_stats))


if __name__ == '__main__':
    main()
