from livetiming.racing import Stat
from livetiming.service import Service as lt_service
from livetiming.service.ris import parse_feed
from livetiming.utils import uncache
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.web.client import Agent, readBody

import argparse
import os
import time


ROOT_URL = 'http://www.ris-timing.be/vitesse/'


def parse_extra_args(eargs):
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--event', help='Event name (from URL)', required=True)
    parser.add_argument('-y', '--year', help='Event year (if not current)', default=time.strftime("%Y"))

    return parser.parse_args(eargs)


def _map_car(car):
    return [
        car.get('num'),
        car.get('state'),
        car.get('class'),
        car.get('driver'),
        car.get('team'),
        car.get('laps'),
        car.get('gap'),
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

        self._data = {
            'series': 'RIS Timing',
            'session': '',
            'timeRemain': 0,
            'cars': []
        }

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
        return {
            "flagState": "green",
            "timeElapsed": 0,
            'timeRemain': self._data['timeRemain']
        }

    @inlineCallbacks
    def _get_raw_feed(self):

        url = uncache(
            os.path.join(
                ROOT_URL,
                self._extra_args.event,
                self._extra_args.year,
                'live.htm'
            )
        )()

        self.log.debug('Getting {url}', url=url)

        response = yield self._agent.request(
            'GET',
            url
        )

        feed = yield readBody(response)

        self._data = parse_feed(feed)

        self._updateAndPublishRaceState()
