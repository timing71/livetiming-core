from livetiming import configure_sentry_twisted, load_env, sentry
from twisted.logger import Logger

from .fetchers import Fetcher, JSONFetcher, MultiLineFetcher
from .factories import Watchdog, ReconnectingWebSocketClientFactory
from .service import AbstractService, BaseService, DuePublisher
from .version import VERSION

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


def get_class(kls):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__(module)
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


def service_name_from(srv):
    if srv.startswith("livetiming."):
        return srv
    return "livetiming.service.plugins.{}.Service".format(srv)


def main():
    load_env()

    args, extra_args = parse_args()

    extra = vars(args)
    extra['extra_args'] = extra_args

    service_class = get_class(service_name_from(args.service_class))

    filepath = os.path.join(
        os.environ.get("LIVETIMING_LOG_DIR", os.getcwd()),
        "{}.log".format(args.service_class)
    )

    with codecs.open(filepath, mode='a', encoding='utf-8') as logFile:
        level = "debug" if args.debug else "info"
        if not args.verbose:  # log to file, not stdout
            txaio.start_logging(out=logFile, level=level)

        logger = Logger()
        logger.info("Live Timing Aggregator version {version}", version=VERSION)
        logger.info("Starting timing service {}...".format(service_class.__module__))
        service = service_class(args, extra_args)
        service.start()


if __name__ == '__main__':
    main()
