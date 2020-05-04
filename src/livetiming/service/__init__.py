from livetiming import configure_sentry_twisted, load_env, sentry, VERSION
from pluginbase import PluginBase
from setuptools import find_namespace_packages
from twisted.logger import Logger

from .fetchers import Fetcher, JSONFetcher, MultiLineFetcher
from .factories import Watchdog, ReconnectingWebSocketClientFactory
from .service import AbstractService, BaseService, DuePublisher

import argparse
import codecs
import os
import sys
import txaio


configure_sentry_twisted()
sentry()


def parse_args(args=None):
    parser = argparse.ArgumentParser(description='Run a Live Timing service.')

    parser.add_argument('service_class', help='Class name of service plugin to run; you may omit the prefix livetiming.service.plugins.')
    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('-r', '--recording-file', nargs='?', help='File to record timing data to')
    parser.add_argument('-d', '--description', nargs='?', help='Service description')
    parser.add_argument('-v', '--verbose', action='store_true', help='Log to stdout rather than a file')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--disable-analysis', action='store_true')
    parser.add_argument('-H', '--hidden', action='store_true', help='Hide this service from the UI except by UUID access')
    parser.add_argument('-N', '--do-not-record', action='store_true', help='Tell the DVR not to keep the recording of this service')
    parser.add_argument('-m', '--masquerade', nargs='?', help='Masquerade as this service class')

    return parser.parse_known_args(args)


def plugin_source_paths():
    return [p for p in sys.path if find_namespace_packages(p, include=['livetiming.service.plugins'])]


def get_plugin_source():
    plugin_base = PluginBase(package='livetiming.service.plugins')
    paths = list(map(lambda p: "{}/livetiming/service/plugins".format(p), plugin_source_paths()))
    plugin_source = plugin_base.make_plugin_source(
        searchpath=paths
    )
    return plugin_source


def main():
    load_env()

    args, extra_args = parse_args()

    extra = vars(args)
    extra['extra_args'] = extra_args

    plugin_source = get_plugin_source()

    filepath = os.path.join(
        os.environ.get("LIVETIMING_LOG_DIR", os.getcwd()),
        "{}.log".format(args.service_class)
    )

    with codecs.open(filepath, mode='a', encoding='utf-8') as logFile:
        level = "debug" if args.debug else "info"
        if not args.verbose:  # log to file, not stdout
            txaio.start_logging(out=logFile, level=level)

        logger = Logger()

        with plugin_source:
            try:
                module = plugin_source.load_plugin(args.service_class)
                service = module.Service(args, extra_args)

                logger.info(
                    "Timing71 version {core} (plugin version {plugin})",
                    core=VERSION,
                    plugin=service.getVersion()
                )
                logger.info(
                    "Starting timing service {clazz}...",
                    clazz=args.service_class
                )
                service.start()
            except ModuleNotFoundError:
                logger.critical(
                    'Unable to find timing service plugin "{clazz}".',
                    clazz=args.service_class
                )
                sys.exit(2)


if __name__ == '__main__':
    main()
