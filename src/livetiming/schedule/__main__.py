from livetiming import load_env
from livetiming.schedule import get_gcal_service

import argparse
import importlib
import os

load_env()

service = get_gcal_service()

COMMANDS = [
    'assist',
    'check',
    'list'
]

parser = argparse.ArgumentParser()

subparsers = parser.add_subparsers()

for cmd in COMMANDS:
    mod = importlib.import_module('livetiming.schedule.{}'.format(cmd))
    if hasattr(mod, 'run') and callable(getattr(mod, 'run')):
        mod_parser = subparsers.add_parser(cmd)
        mod_parser.set_defaults(func=getattr(mod, 'run'))
        if hasattr(mod, 'add_parser_args') and callable(getattr(mod, 'add_parser_args')):
            getattr(mod, 'add_parser_args')(mod_parser)

args = parser.parse_args()

args.func(service, args)
