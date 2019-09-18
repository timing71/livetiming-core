from livetiming.orchestration.schedule import get_events
from livetiming.orchestration.scheduler import EVT_SERVICE_REGEX
from livetiming.service import get_plugin_source

import importlib


class BadEventException(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message


def run(service, _):
    events = get_events(service)

    all_ok = True

    plugin_source = get_plugin_source()

    for event in events:
        try:
            _check_event(event['summary'], plugin_source)
        except BadEventException as e:
            print(e.message, event)
            all_ok = False

    if all_ok:
        print("{} event{} all OK".format(
            len(events),
            '' if len(events) == 1 else 's'
        ))
    else:
        print("Some events failed validation. See details above.")


def _check_event(summary, plugin_source):
    match = EVT_SERVICE_REGEX.match(summary)
    if not match:
        raise BadEventException("Invalid event format")

    service = match.group('service')

    try:
        with plugin_source:
            mod = plugin_source.load_plugin(service)
            if not hasattr(mod, 'Service'):
                raise BadEventException('Event service class does not exist')
    except:
        raise BadEventException('Event service module does not exist')
