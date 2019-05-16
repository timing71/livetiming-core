from .constants import Channels
from .socketio import WebsocketOnlySocketIO
from socketIO_client import BaseNamespace
from threading import Thread
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from twisted.web.client import Agent, readBody

import simplejson


def create_client(namespace, profile, on_ready=None, log=Logger()):
    class Client(BaseNamespace):
        def __init__(self, *args, **kwargs):
            super(Client, self).__init__(*args, **kwargs)

            self._data = {}
            self._meta = {}

            self._agent = Agent(reactor)

        def on_connect(self):
            log.info("Client connected")

        def on_ready(self):
            self.join(Channels.SEASONS, with_season=False, callback=on_ready)

        def _channel(self, channel, with_season=True):
            if isinstance(channel, Channels):
                channel = channel.value

            if with_season:
                season_key = self._channel(Channels.SEASONS, False)
                season = self._data.get(season_key, {}).get('CurrentSeason')
                if season:
                    season = '_{}'.format(season)
            else:
                season = ''

            return '{}|{}{}{}'.format(
                namespace,
                profile,
                season,
                channel
            )

        def _handle_metadata(self, data, channel, callback=None):
            log.debug("Handing metadata: {channel} {data}", channel=channel, data=data)
            requires_fetch = channel not in self._meta or self._meta[channel]['CurrentSync'] != data['CurrentSync']
            self._meta[channel] = data
            if requires_fetch:
                url_to_fetch = '{}{}.json?s={}'.format(
                    data['CachingClusterURL'],
                    channel.replace('|', '/'),
                    data['CurrentSync']
                )
                log.debug("Requires fetch: {url}", url=url_to_fetch)
                self._fetch_data(channel, url_to_fetch, callback)

        @inlineCallbacks
        def _fetch_data(self, channel, url, callback):
            response = yield self._agent.request('GET', url)
            body = yield readBody(response)
            parsed = simplejson.loads(body)
            self._apply_data(channel, parsed)
            if callback:
                callback(self._data[channel])

        def _apply_data(self, channel, data):
            content = data.get('content', {})
            if 'full' in content:
                self._data[channel] = content['full']
            else:
                log.error("I don't know how to handle partial content yet!")
                print data

        def join(self, channel, with_season=True, callback=None):

            def my_callback(data, channel):
                self._handle_metadata(data, channel, callback)

            full_channel = self._channel(channel, with_season)
            log.info("Joining {channel}", channel=full_channel)
            self.emit(
                'join',
                full_channel,
                callback=my_callback
            )

        def get_current_season(self, callback):
            self.join(Channels.SEASON, callback=callback)

        def get_schedule(self, meeting_id, callback):
            self.join(
                Channels.SCHEDULE.formatted_value(meeting_id=meeting_id.upper()),
                callback=callback
            )

        def get_timing(self, session_id, callback):
            self.join(
                Channels.TIMING.formatted_value(session_id=session_id.upper()),
                callback=callback
            )

        def get_comp_detail(self, session_id, callback):
            self.join(
                Channels.COMP_DETAIL.formatted_value(session_id=session_id.upper()),
                callback=callback
            )

    return Client


def start_client(client):
    sio = WebsocketOnlySocketIO(
        'https://livestats-lb.sportresult.com',
        Namespace=client,
        transports=['websocket'],
        verify=False
    )

    socketThread = Thread(target=sio.wait)
    socketThread.daemon = True
    socketThread.start()

    return sio.get_namespace()
