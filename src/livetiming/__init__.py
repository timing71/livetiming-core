from dotenv import load_dotenv, find_dotenv
from twisted.python import log

import os
import pkg_resources
import raven


def load_env():
    try:
        maybe_dotenv = find_dotenv("livetiming.env", raise_error_if_not_found=True, usecwd=True)
        load_dotenv(maybe_dotenv)
    except IOError:
        pass


_sentry = None


def sentry():
    global _sentry
    if not _sentry:
        _sentry = raven.Client(
            environment=os.getenv("LIVETIMING_ENVIRONMENT", "development"),
            include_paths=['livetiming'],
            release=raven.fetch_package_version('livetiming'),
        )
    return _sentry


def _log_to_sentry(event):
    if not event.get('isError') or 'failure' not in event:
        return

    f = event['failure']
    sentry().captureException((f.type, f.value, f.getTracebackObject()))


_sentry_twisted_configured = False


def configure_sentry_twisted():
    global _sentry_twisted_configured
    if not _sentry_twisted_configured:
        log.addObserver(_log_to_sentry)
        _sentry_twisted_configured = True
