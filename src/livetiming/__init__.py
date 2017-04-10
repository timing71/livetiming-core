from dotenv import load_dotenv, find_dotenv
from raven import Client
from twisted.python import log


import os
import pkg_resources


__version__ = pkg_resources.require('livetiming')[0].version


def load_env():
    try:
        maybe_dotenv = find_dotenv("livetiming.env", raise_error_if_not_found=True, usecwd=True)
        load_dotenv(maybe_dotenv)
    except IOError:
        pass


def sentry():
    return Client(
        include_paths=[__name__.split('.', 1)[0]],
        release=__version__
    )


def version():
    return __version__
