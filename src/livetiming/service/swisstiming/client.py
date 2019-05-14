from .constants import Channels
from threading import Thread
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger
from twisted.web.client import Agent, readBody

import simplejson
import socketio


class Client(object):

    def __init__(self, namespace, profile):
        self.namespace = namespace
        self.profile = profile

        self._data = {}
        self._meta = {}

        self._agent = Agent(reactor)
        self._sio = self._create_sio()

    def _create_sio(self):
        sio = socketio.Client(logger=True)

        @sio.on('ready')
        def on_ready():
            self.join(Channels.SEASONS, with_season=False)

        return sio

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
            self.namespace,
            self.profile,
            season,
            channel
        )

    def _handle_metadata(self, data, channel, callback=None):
        print "Handing metadata: {} {}".format(channel, data)
        requires_fetch = channel not in self._meta or self._meta[channel]['CurrentSync'] != data['CurrentSync']
        self._meta[channel] = data
        if requires_fetch:
            url_to_fetch = '{}{}.json?s={}'.format(
                data['CachingClusterURL'],
                channel.replace('|', '/'),
                data['CurrentSync']
            )
            print "Requires fetch: {}".format(url_to_fetch)
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
            print "I don't know how to handle partial content yet!"
            print data

    def join(self, channel, with_season=True, callback=None):

        def my_callback(data, channel):
            self._handle_metadata(data, channel, callback)

        self._sio.emit(
            'join',
            self._channel(channel, with_season),
            callback=my_callback
        )

    def start(self, in_thread=True):
        self._sio.connect(
            'https://livestats-lb.sportresult.com',
            transports=['websocket']
        )

        if in_thread:
            socketThread = Thread(target=self._sio.wait)
            socketThread.daemon = True
            socketThread.start()
        else:
            self._sio.wait()

    def get_current_season(self, callback):
        self.join(Channels.SEASON, callback=callback)

    def get_schedule(self, meeting_id, callback):
        self.join(
            Channels.SCHEDULE.formatted_value(meeting_id=meeting_id.upper()),
            callback
        )

    def get_timing(self, session_id, callback):
        self.join(
            Channels.TIMING.formatted_value(session_id=session_id.upper()),
            callback
        )

    def get_comp_detail(self, session_id, callback):
        self.join(
            Channels.COMP_DETAIL.formatted_value(session_id=session_id.upper()),
            callback
        )
