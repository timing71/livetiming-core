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


def sentry():
    return raven.Client(
        environment=os.getenv("LIVETIMING_ENVIRONMENT", "development"),
        include_paths=['livetiming'],
        release=raven.fetch_package_version('livetiming'),
    )
