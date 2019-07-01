import datetime
import os
import re

from livetiming.schedule import create_event, get_events
from livetiming.schedule.datetime_z import parse_datetime
from livetiming.scheduler import EVT_SERVICE_REGEX

DEFAULT_CALENDAR_URL = os.environ.get(
    'CALENDAR_SOURCE_URL',
    'eecbbdriq2erv62pbk1t7mnvqqcdook2@import.calendar.google.com'
)

TAG_TO_SERVICE_CLASS = {
    '24H Proto Series': '24h_series',
    '24H Series': '24h_series',
    '24H TCES': '24h_series',
    '24H': '24h_series',
    'Blancpain GT': 'blancpain',
    'CTSC': 'imsa',
    'European Le Mans': 'elms',
    'ELMS': 'elms',
    'Formula 1': 'f1',
    'F1': 'f1',
    'Formula 2': 'f2',
    'F2': 'f2',
    'Formula E': 'formulae',
    'GP3 Series': 'f3',
    'F3': 'f3',
    'IMSA': 'imsa',
    'IndyCar': 'indycar',
    'Michelin Le Mans Cup': 'lemanscup',
    'V8 Supercars': 'v8sc',
    'Supercars': 'v8sc',
    'VLN': 'vln',
    'WEC': 'wec'
}

ALWAYS_HIDDEN_SERVICES = ['f1', 'formulae']


def add_parser_args(parser):
    parser.add_argument('--calendar', default=DEFAULT_CALENDAR_URL, help='Google calendar URL to source events from')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t actually create events')


def run(service, args):
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    then = (datetime.datetime.utcnow() + datetime.timedelta(days=14)).isoformat() + 'Z'
    upcoming = service.events().list(
        calendarId=args.calendar,
        orderBy='startTime',
        timeMin=now,
        timeMax=then,
        singleEvents=True
    ).execute().get('items', [])

    scheduled = list(map(_parse_scheduled_event, get_events(service)))

    def already_scheduled(event):
        for scheduled_event in scheduled:
            if event['id'] == scheduled_event['correlationId']:
                return True
            if event['service'] == scheduled_event['service']:
                if event['start'] == scheduled_event['start']:
                    if event['end'] == scheduled_event['end']:
                        return True
        return False

    for e in upcoming:
        if 'dateTime' not in e['start']:
            print("Skipping event without session time: {}".format(e['summary']))
        else:
            event = _parse_event(e)

            if not event['service']:
                print("Skipping event with no associated service: {}".format(e['summary']))
            elif event['summary'].endswith('Event'):
                print("Skipping event without session time: {}".format(e['summary']))
            elif already_scheduled(event):
                print("Already scheduled: {}".format(e['summary']))
            else:
                print("New event: {} ({} - {})".format(event['summary'], event['start'], event['end']))

                event_body = {
                    'summary': "{} [{}{}]".format(
                        event['summary'],
                        event['service'],
                        ',--hidden' if event['service'] in ALWAYS_HIDDEN_SERVICES else ''
                    ),
                    'start': {
                        'dateTime': event['start'].strftime("%Y-%m-%dT%H:%M:%S%z")
                    },
                    'end': {
                        'dateTime': event['end'].strftime("%Y-%m-%dT%H:%M:%S%z")
                    },
                    'description': 'Automatically generated by livetiming-schedule assist',
                    'extendedProperties': {
                        'private': {
                            'correlationId': e['id']
                        }
                    }
                }
                if not args.dry_run:
                    create_event(service, event_body)


MULTI_SPACE_REGEX = re.compile('\s+')


def _parse_event(event):
    summary = event['summary']
    tag = summary[1:summary.index(']')]

    return {
        'summary': MULTI_SPACE_REGEX.sub(' ', "{}: {}".format(tag, summary[summary.index(']') + 1:])),
        'service': TAG_TO_SERVICE_CLASS.get(tag),
        'start': parse_datetime(event['start']['dateTime']),
        'end': parse_datetime(event['end']['dateTime']),
        'id': event['id']
    }


def _parse_scheduled_event(event):
    parsed = EVT_SERVICE_REGEX.match(event['summary'])

    return {
        'summary': parsed.group('name'),
        'service': parsed.group('service'),
        'start': parse_datetime(event['start']['dateTime']),
        'end': parse_datetime(event['end']['dateTime']),
        'correlationId': event.get('extendedProperties', {}).get('private', {}).get('correlationId')
    }
