from livetiming.racing import Stat
from livetiming.service import Service as lt_service
from livetiming.service.ris import parse_feed
from livetiming.utils import uncache
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.web.client import Agent, readBody

import argparse
import datetime
import dateutil.parser
import os
import time


ROOT_URL = 'http://www.ris-timing.be/vitesse/'


def parse_extra_args(eargs):
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--event', help='Event name (used to create URL)')
    parser.add_argument('-u', '--url', help='Full URL of timing page')
    parser.add_argument('-y', '--year', help='Event year (if not current)', default=time.strftime("%Y"))

    return parser.parse_args(eargs)


def _map_car(car):
    return [
        car.get('num'),
        car.get('state'),
        car.get('class'),
        car.get('driver') or '',
        car.get('team'),
        car.get('laps'),
        car.get('gap') or '',
        car.get('s1'),
        car.get('s2'),
        car.get('s3'),
        car.get('last_lap'),
        car.get('best_lap'),
        car.get('pits')
    ]


class Service(lt_service):
    attribution = ['RIS Timing', 'http://ris-timing.be/']
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self._extra_args = parse_extra_args(extra_args)

        if not self._extra_args.event and not self._extra_args.url:
            raise Exception('Either event or URL must be specified!')

        self._data = {
            'series': 'RIS Timing',
            'session': '',
            'timeRemain': 0,
            'cars': []
        }

        self._last_modified = None

        self._agent = Agent(reactor)

    def getName(self):
        return self._data.get('series', 'RIS Timing')

    def getDefaultDescription(self):
        return self._data.get('session', '')

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.LAPS,
            Stat.GAP,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getPollInterval(self):
        return 5

    def start(self):
        LoopingCall(self._get_raw_feed).start(5)
        super(Service, self).start()

    def getRaceState(self):
        return {
            'cars': self._map_cars(),
            'session': self._map_session()
        }

    def _map_cars(self):
        return map(_map_car, self._data['cars'])

    def _map_session(self):

        time_remain = self._data.get('timeRemain', 0)

        if self._last_modified:
            now = datetime.datetime.utcnow()
            delta = (now - self._last_modified).total_seconds()
            time_remain -= delta

        return {
            "flagState": "green",
            "timeElapsed": 0,
            'timeRemain': max(0, time_remain)
        }

    @inlineCallbacks
    def _get_raw_feed(self):

        url_base = self._extra_args.url or os.path.join(
            ROOT_URL,
            self._extra_args.event,
            self._extra_args.year,
            'live.htm'
        )

        url = uncache(url_base)()

        self.log.debug('Getting {url}', url=url)

        response = yield self._agent.request(
            'GET',
            url
        )

        prev_series = self._data.get('series')
        prev_session = self._data.get('session')

        if response.code == 200:

            try:
                feed = yield readBody(response)

                self._data = parse_feed(feed)
                self._last_modified = dateutil.parser.parse(response.headers.getRawHeaders('last-modified')[0])
                self._last_modified = self._last_modified.replace(tzinfo=None) - self._last_modified.utcoffset()

                session_change = prev_series != self._data.get('series') or prev_session != self._data.get('session')
                if session_change:
                    self.publishManifest()
                    if self.analyser:
                        self.analyser.reset()

                self._updateAndPublishRaceState()
            except Exception as e:
                print 'FAIL'
                self.log.error(e)
        else:
            self.log.warn("Received error {code} when fetching URL {url}", code=response.code, url=url)
