from autobahn.wamp.types import PublishOptions
from collections import OrderedDict
from livetiming.analysis.data import DataCentre
from livetiming.network import Message, MessageClass
from livetiming.racing import FlagStatus, Stat
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

import copy
import cPickle
import importlib
import simplejson
import time
import os


ANALYSIS_PUBLISH_INTERVAL = 60
MIN_PUBLISH_INTERVAL = 10


def _make_data_message(data):
    return Message(
        MessageClass.ANALYSIS_DATA,
        simplejson.loads(simplejson.dumps(data)),
        retain=True
    ).serialise()


PROCESSING_MODULES = [  # Order is important!
    'car',
    'driver',
    'lap',
    'stint',
    'session'
]

EMPTY_STATE = {
    'cars': [],
    'session': {
        'flagState': 'none'
    }
}


class Analyser(object):
    log = Logger()
    publish_options = PublishOptions(retain=True)

    def __init__(self, uuid, publishFunc, interval=ANALYSIS_PUBLISH_INTERVAL):
        self._current_state = copy.copy(EMPTY_STATE)
        self.uuid = uuid
        self.publish = publishFunc
        self.interval = max(interval, MIN_PUBLISH_INTERVAL)
        self._load_data_centre()
        self._pending_publishes = {}
        self._last_published = {}

        self._modules = {m: importlib.import_module("livetiming.analysis.{}".format(m)) for m in PROCESSING_MODULES}

    def receiveStateUpdate(self, newState, colSpec, timestamp=None):
        if not timestamp:
            timestamp = time.time()
        self.data_centre.current_state = copy.deepcopy(newState)
        for key, module in self._modules.iteritems():
            if module.receive_state_update(self.data_centre, self._current_state, newState, colSpec, timestamp):
                self._publish_data(key, module.get_data(self.data_centre))

        self._current_state = self.data_centre.current_state
        self.data_centre.latest_timestamp = timestamp

    def _publish_data(self, key, data):
        self.log.debug("Queueing publish of data '{key}': {data}", key=key, data=data)
        self._pending_publishes[key] = data
        self._publish_pending()

    @inlineCallbacks
    def _publish_pending(self):
        now = time.time()
        for key, data in copy.copy(self._pending_publishes).iteritems():
            if self._last_published.get(key, 0) + (self.interval or 1) < now and self.publish:
                self.log.debug("Publishing queued data for {key}", key=key)
                did_publish = yield self.publish(
                    u"livetiming.analysis/{}/{}".format(self.uuid, key),
                    _make_data_message(data),
                    options=self.publish_options
                )
                if did_publish:
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
        duration = time.time() - start
        if duration < 0.5:
            self.log.debug("Analysis state saved in {secs} seconds", secs=duration)
        elif duration < 1:
            self.log.info("Analysis state saved in {secs} seconds", secs=duration)
        else:
            self.log.warn("Analysis state saved in {secs} seconds", secs=duration)

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
        self._current_state = copy.copy(EMPTY_STATE)


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.mapping = {}
        for idx, col in enumerate(colSpec):
            self.mapping[col] = idx

    def get(self, car, field, default=None):
        if car:
            try:
                return car[self.mapping[field]]
            except KeyError:
                return default
        return default


def per_car(func):
    def inner(dc, old_state, new_state, colspec, timestamp):
        flag = FlagStatus.fromString(new_state["session"].get("flagState", "none"))
        f = FieldExtractor(colspec)
        result = False
        for idx, new_car in enumerate(new_state['cars']):
            race_num = f.get(new_car, Stat.NUM)
            if race_num:
                old_car = next(iter([c for c in old_state["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)
                result = func(dc, race_num, idx + 1, old_car, new_car, f, flag, timestamp) or result
        return result
    return inner


def map_stint_with(car, timestamp):
    drivers = car.drivers

    def map_stint(stint):
        if not stint:
            return None
        return [
            stint.start_lap,
            stint.start_time,
            stint.end_lap if not stint.in_progress else car.current_lap,
            stint.end_time if not stint.in_progress else timestamp,
            stint.in_progress,
            drivers.index(stint.driver) if stint.driver in drivers else -1,
            stint.best_lap_time,
            stint.yellow_laps,
            stint.average_lap_time,
            map(lambda ls: ls.for_json(), stint.laps)
        ]
    return map_stint
