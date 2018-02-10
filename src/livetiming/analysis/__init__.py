from autobahn.wamp.types import PublishOptions
from collections import OrderedDict
from livetiming import sentry
from livetiming.analysis.data import DataCentre
from livetiming.analysis import session
from livetiming.network import Message, MessageClass
from lzstring import LZString
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
import simplejson
import time
import copy
import cPickle
import os


sentry = sentry()

ANALYSIS_PUBLISH_INTERVAL = 60


def _make_data_message(data):
    return Message(
        MessageClass.ANALYSIS_DATA,
        simplejson.loads(simplejson.dumps(data)),
        retain=True
    ).serialise()


PROCESSING_MODULES = {
    'session': session
}


class Analyser(object):
    log = Logger()
    publish_options = PublishOptions(retain=True)

    def __init__(self, uuid, publishFunc, interval=ANALYSIS_PUBLISH_INTERVAL):
        self._current_state = None
        self.uuid = uuid
        self.publish = publishFunc
        self.interval = interval
        self._load_data_centre()
        self._pending_publishes = {}
        self._last_published = {}

    def receiveStateUpdate(self, newState, colSpec, timestamp=None):
        if not timestamp:
            timestamp = time.time()
        if self._current_state:
            for key, module in PROCESSING_MODULES.iteritems():
                if module.receiveStateUpdate(self.data_centre, self._current_state, newState, colSpec, timestamp):
                    self._publish_data(key, module.get_data(self.data_centre))

        self._current_state = copy.deepcopy(newState)
        self.data_centre.latest_timestamp = timestamp

    def _publish_data(self, key, data):
        self.log.debug("Queueing publish of data '{key}': {data}", key=key, data=data)
        self._pending_publishes[key] = data

    def _publish_pending(self):
        now = time.time()
        for key, data in copy.copy(self._pending_publishes.iteritems()):
            if self._last_published.get(key, 0) + self.interval < now:
                self.publish(
                    u"livetiming.analysis/{}/{}".format(self.uuid, key),
                    _make_data_message(data),
                    options=self.publish_options
                )
                self._pending_publishes.pop(key)
                self._last_published[key] = now

    def _data_centre_file(self):
        return os.path.join(
            os.environ.get("LIVETIMING_ANALYSIS_DIR", os.getcwd()),
            "{}.data.p".format(self.uuid)
        )

    def save_data_centre(self):
        start = time.time()
        with open(self._data_centre_file(), "wb") as data_dump_file:
            cPickle.dump(self.data_centre, data_dump_file, cPickle.HIGHEST_PROTOCOL)
        self.log.info("Analysis state saved in {secs} seconds", secs=(time.time() - start))

    def _load_data_centre(self):
        try:
            with open(self._data_centre_file(), "rb") as data_dump_file:
                self.log.info("Using existing data centre dump from {}".format(os.path.realpath(data_dump_file.name)))
                self.data_centre = cPickle.load(data_dump_file)
        except IOError:
            self.data_centre = DataCentre()

    def reset(self):
        self.data_centre.reset()
        self._pending_publishes = {}
        self._last_published = {}


def per_car(func):
    def inner(dc, old_state, new_state, colspec, timestamp):
        f = FieldExtractor(colSpec)
        result = False
        for idx, new_car in enumerate(newState['cars']):
            race_num = f.get(new_car, Stat.NUM)
            if race_num:
                old_car = next(iter([c for c in oldState["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)
                if old_car:
                    result = result or func(dc, old_car, new_car, f, timestamp)
        return result
    return inner
