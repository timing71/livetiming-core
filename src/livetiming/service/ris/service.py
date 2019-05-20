from livetiming.racing import Stat
from livetiming.service import Service as lt_service
from twisted.internet.task import LoopingCall

import argparse
import time


ROOT_URL = 'http://www.ris-timing.be/vitesse/'


def parse_extra_args(eargs):
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--event', help='Event name (from URL)', required=True)
    parser.add_argument('-y', '--year', help='Event year (if not current)', default=time.strftime("%Y"))

    return parser.parse_args(eargs)


class Service(lt_service):
    attribution = ['RIS Timing', 'http://ris-timing.be/']
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self._extra_args = parse_extra_args(extra_args)

        self._data = {
            'cars': []
        }

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
        return []

    def _map_session(self):
        return {
            "flagState": "none",
            "timeElapsed": 0
        }

    def _get_raw_feed(self):
        self.log.info("Pretending to get raw feed")
        self._updateAndPublishRaceState()
