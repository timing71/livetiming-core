from autobahn.wamp.types import PublishOptions
from collections import OrderedDict
from livetiming.analysis.data import DataCentre
from livetiming.network import Message, MessageClass
from livetiming.racing import FlagStatus, Stat
from twisted.internet.defer import DeferredLock, inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

import copy
import pickle
import importlib
import simplejson
import time
import os


ANALYSIS_PUBLISH_INTERVAL = 60
MIN_PUBLISH_INTERVAL = 10


def _make_data_message(data, retain=True):
    return Message(
        MessageClass.ANALYSIS_DATA,
        data,
        retain
    ).serialise()


PROCESSING_MODULES = [  # Order is important!
    'static',
    'driver',
    'car',
    'messages',  # 163k without, 309k with. I'll take that.
    'session'
]

EMPTY_STATE = {
    'cars': [],
    'session': {
        'flagState': 'none'
    }
}


def with_dc_lock(func):
    def inner(elf, *args, **kwargs):
        elf._dc_lock.run(func, elf, *args, **kwargs)
    return inner


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
        self._dc_lock = DeferredLock()

        self._modules = {m: importlib.import_module("livetiming.analysis.{}".format(m)) for m in PROCESSING_MODULES}

    @with_dc_lock
    def receiveStateUpdate(self, newState, colSpec, timestamp=None, new_messages=[]):
        if not timestamp:
            timestamp = time.time()
        self.data_centre.current_state = copy.deepcopy(newState)
        for key in PROCESSING_MODULES:
            module = self._modules[key]
            updates = module.receive_state_update(self.data_centre, self._current_state, newState, colSpec, timestamp, new_messages)
            for key, data in updates:
                self._publish_data(key, data)

        self._current_state = self.data_centre.current_state
        self.data_centre.latest_timestamp = timestamp

    def publish_all(self):
            for key, module in self._modules.items():
                self._publish_data(key, module.get_data(self.data_centre))

    def _publish_data(self, key, data):
        self.log.debug("Queueing publish of data '{key}'", key=key, data=data)
        self._pending_publishes[key] = data
        self._publish_pending()

    def _publish_pending(self):
        now = time.time()
        for key, data in copy.copy(self._pending_publishes).items():
            if self._last_published.get(key, 0) + (self.interval or 1) < now and self.publish:
                self.log.debug("Publishing queued data for livetiming.analysis/{uuid}/{key}", uuid=self.uuid, key=key)
                retain = key not in ['lap', 'stint']
                self.publish(
                    "livetiming.analysis/{}/{}".format(self.uuid, key),
                    _make_data_message(data, retain),
                    options=self.publish_options if retain else None
                )
                self._pending_publishes.pop(key)
                self._last_published[key] = now

    def _data_centre_file(self):
        return os.path.join(
            os.environ.get("LIVETIMING_ANALYSIS_DIR", os.getcwd()),
            "{}.data.p".format(self.uuid)
        )

    @with_dc_lock
    def save_data_centre(self):
        start = time.time()
        with open(self._data_centre_file(), "wb") as data_dump_file:
            pickle.dump(self.data_centre, data_dump_file, pickle.HIGHEST_PROTOCOL)
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
                self.data_centre = pickle.load(data_dump_file)
        except IOError:
            self.data_centre = DataCentre()

    @with_dc_lock
    def reset(self):
        self.data_centre.reset()
        self._pending_publishes = {}
        self._last_published = {}
        self._current_state = copy.copy(EMPTY_STATE)

    def get_current_state(self):
        data = {}

        for key, module in self._modules.items():
            data[key] = module.get_data(self.data_centre)

        car_stats = data.pop('car')
        for k, v in car_stats.items():
            data[k] = v

        return data


class FieldExtractor(object):
    def __init__(self, colSpec):
        self.mapping = {}
        for idx, col in enumerate(colSpec):
            self.mapping[col] = idx

    def get(self, car, field, default=None):
        if car:
            try:
                return car[self.mapping[field]]
            except (KeyError, IndexError):
                return default
        return default


def per_car(key, data_func):
    def per_car_inner(func):
        def inner(dc, old_state, new_state, colspec, timestamp, new_messages):
            flag = FlagStatus.fromString(new_state["session"].get("flagState", "none"))
            f = FieldExtractor(colspec)
            changed = False
            for idx, new_car in enumerate(new_state['cars']):
                race_num = f.get(new_car, Stat.NUM)
                if race_num:
                    old_car = next(iter([c for c in old_state["cars"] if f.get(c, Stat.NUM) == race_num] or []), None)
                    changed = func(dc, race_num, idx + 1, old_car, new_car, f, flag, timestamp, new_messages) or changed
            if changed:
                return [(key, data_func(dc))]
            else:
                return []
        return inner
    return per_car_inner


def map_stint_with(car, timestamp):
    drivers = car.drivers

    def map_stint(stint):
        if not stint:
            return None
        return [
            int(stint.start_lap) if stint.start_lap else None,
            stint.start_time,
            int(stint.end_lap) if not stint.in_progress else int(car.current_lap),
            stint.end_time if not stint.in_progress else timestamp,
            stint.in_progress,
            drivers.index(stint.driver) if stint.driver in drivers else -1,
            stint.best_lap_time,
            stint.yellow_laps,
            stint.average_lap_time,
            [ls.for_json() for ls in stint.laps]
        ]
    return map_stint
