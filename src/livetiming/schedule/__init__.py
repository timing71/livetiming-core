import argparse
import datetime
import httplib2
import os

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

# If modifying these scopes, delete your previously saved credentials
SCOPES = 'https://www.googleapis.com/auth/calendar'
CLIENT_SECRET_FILE = 'gcal_client_secret.json'
APPLICATION_NAME = 'Live Timing Aggregator scheduler helpers'


def _get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-lt-schedule-helpers.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else:  # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to {}'.format(credential_path))
    return credentials


def get_gcal_service():
    credentials = _get_credentials()
    http = credentials.authorize(httplib2.Http())
    return discovery.build('calendar', 'v3', http=http)


def get_events(service):
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    return service.events().list(
        calendarId=os.environ['LIVETIMING_CALENDAR_ID'],
        orderBy='startTime',
        timeMin=now,
        singleEvents=True
    ).execute().get('items', [])


def create_event(service, event_body):
    service.events().insert(
        calendarId=os.environ['LIVETIMING_CALENDAR_ID'],
        body=event_body
    ).execute()
