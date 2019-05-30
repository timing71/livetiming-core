from .constants import Channels
from .data import patch
from .message import parse_message
from .socketio import WebsocketOnlySocketIO
from socketIO_client import BaseNamespace
from threading import Thread
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from twisted.web.client import Agent, readBody

import simplejson


FETCH_RETRIES = 2


def create_client(namespace, profile, on_ready=None, log=Logger()):
    class Client(BaseNamespace):
        def __init__(self, *args, **kwargs):
            super(Client, self).__init__(*args, **kwargs)

            self._data = {}
            self._meta = {}
            self._callbacks = {}

            self._agent = Agent(reactor)

        def on_connect(self):
            log.info("Client connected")

        def on_ready(self):
            self.join(Channels.SEASONS, with_season=False, callback=on_ready)

        def on_message(self, data):
            parsed = parse_message(data)
            if parsed:
                self._handle_async_data(parsed)

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

        def _handle_metadata(self, data, channel):
            log.debug("Handing metadata: {channel} {data}", channel=channel, data=data)
            requires_fetch = channel not in self._meta or self._meta[channel]['CurrentSync'] != data['CurrentSync']
            self._meta[channel] = data
            if requires_fetch:
                url_to_fetch = '{}{}.json?s={}'.format(
                    data['CachingClusterURL'],
                    channel.replace('|', '/'),
                    data.get('CurrentSync', 0)
                )
                log.debug("Requires fetch: {url}", url=url_to_fetch)
                self._fetch_data(channel, url_to_fetch)

        def _handle_async_data(self, data):
            channel = data['Channel']
            if channel in self._meta:
                meta = self._meta[channel]

                requires_fetch = meta.get('CurrentSync') != data.get('sync')
                if requires_fetch:
                    url_to_fetch = '{}{}/{}.json'.format(
                        meta['CachingClusterURL'],
                        channel.replace('|', '/'),
                        data['sync']
                    )
                    log.debug("Requires fetch: {url}", url=url_to_fetch)
                    self._fetch_data(channel, url_to_fetch)

        @inlineCallbacks
        def _fetch_data(self, channel, url, tries_remaining=FETCH_RETRIES):

            url = '{}?t={}'.format(
                url,
                FETCH_RETRIES - tries_remaining
            )

            response = yield self._agent.request('GET', url)
            try:
                if response.code == 200:
                    body = yield readBody(response)
                    parsed = simplejson.loads(body)
                    self._apply_data(channel, parsed)
                    if channel in self._callbacks:
                        cb = self._callbacks[channel]
                        cb(self._data[channel])
                    return
            except Exception as e:
                log.error('Exception retrieving data: {e}', e=e)
            log.debug("Received response code {code} for URL {url} ({i} tries remaining)", code=response.code, url=url, i=tries_remaining)
            if tries_remaining > 0:
                reactor.callLater(0.5, self._fetch_data, channel, url, tries_remaining - 1)
            else:
                log.error("Received response code {code} for URL {url} ({i} tries remaining)", code=response.code, url=url, i=tries_remaining)

        def _apply_data(self, channel, data):
            content = data.get('content', {})
            if 'full' in content:
                self._data[channel] = content['full']
            else:
                try:
                    patch(self._data[channel], data)
                except Exception as e:
                    log.error(
                        'Failed to apply patch! Original data was {orig}, patch was {patch}, error was {exc}',
                        orig=self._data[channel],
                        patch=data,
                        exc=e
                    )

        def join(self, channel, with_season=True, callback=None):

            full_channel = self._channel(channel, with_season)
            log.debug("Joining {channel}", channel=full_channel)

            if callback:
                self._callbacks[full_channel] = callback

            self.emit(
                'join',
                full_channel,
                callback=self._handle_metadata
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
