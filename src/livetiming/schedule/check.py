from livetiming.schedule import get_events
from livetiming.scheduler import EVT_SERVICE_REGEX

import importlib


class BadEventException(Exception):
    pass


def run(service, _):
    events = get_events(service)

    all_ok = True

    for event in events:
        try:
            _check_event(event['summary'])
        except BadEventException as e:
            print e.message, event
            all_ok = False

    if all_ok:
        print "{} event{} all OK".format(
            len(events),
            '' if len(events) == 1 else 's'
        )
    else:
        print "Some events failed validation. See details above."


def _check_event(summary):
    match = EVT_SERVICE_REGEX.match(summary)
    if not match:
        raise BadEventException("Invalid event format")

    service = match.group('service')
    try:
        mod = importlib.import_module('livetiming.service.{}'.format(service))
        if not hasattr(mod, 'Service'):
            raise BadEventException('Event service class does not exist')
    except:
        raise BadEventException('Event service module does not exist')
