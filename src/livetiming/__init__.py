from dotenv import load_dotenv, find_dotenv
from twisted.python import log

import os
import pkg_resources
import sentry_sdk


def load_env():
    try:
        maybe_dotenv = find_dotenv("livetiming.env", raise_error_if_not_found=True, usecwd=True)
        load_dotenv(maybe_dotenv)
    except IOError:
        pass


_sentry_configured = False


def sentry():
    global _sentry_configured
    if not _sentry_configured:
        sentry_sdk.init(
            environment=os.getenv("LIVETIMING_ENVIRONMENT", "development"),
            release=pkg_resources.get_distribution('livetiming').version,
        )
        _sentry_configured = True


def _log_to_sentry(event):
    if not event.get('isError') or 'failure' not in event:
        return

    f = event['failure']
    with sentry_sdk.push_scope() as scope:
        scope.set_extra('debug', False)
        sentry_sdk.capture_exception((f.type, f.value, f.getTracebackObject()))


_sentry_twisted_configured = False


def configure_sentry_twisted():
    global _sentry_twisted_configured
    if not _sentry_twisted_configured:
        log.addObserver(_log_to_sentry)
        _sentry_twisted_configured = True
