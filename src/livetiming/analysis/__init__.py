from autobahn.wamp.types import PublishOptions
from collections import OrderedDict
from livetiming import sentry
from livetiming.analysis.data import DataCentre
from livetiming.network import Message, MessageClass
from lzstring import LZString
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
    return Message(MessageClass.ANALYSIS_DATA, simplejson.dumps(data), retain=True).serialise()


class Analyser(object):
    log = Logger()

    def __init__(self, uuid, publishFunc, modules=[], publish=True, interval=ANALYSIS_PUBLISH_INTERVAL):
        for m in modules:
            if not issubclass(m, Analysis):
                raise RuntimeError("Supplied {} is not derived from class Analysis".format(m.__name__))
        self.uuid = uuid
        self.publish = publishFunc
        self._load_data_centre()
        self.modules = OrderedDict()
        for mclass in modules:
            self.modules[_fullname(mclass)] = mclass(self.data_centre)

        if publish:
            LoopingCall(self._publishAnalysisData).start(max(interval, ANALYSIS_PUBLISH_INTERVAL), False)

    def receiveStateUpdate(self, newState, colSpec, timestamp=None):
        self.data_centre.update_state(newState, colSpec, timestamp)

    def _publishAnalysisData(self):
        if self.data_centre.current_state["session"].get("flagState", "none") != "none":
            start_time = time.time()
            publish_options = PublishOptions(retain=True)
            for mclass, module in self.modules.iteritems():
                try:
                    self.publish(
                        u"livetiming.analysis/{}/{}".format(self.uuid, mclass[20:]),
                        _make_data_message(module.getData()),
                        options=publish_options
                    )
                except Exception:
                    self.log.failure("Exception while publishing update from analysis module {mclass}: {log_failure}", mclass=mclass)
                    sentry.captureException()
            duration = time.time() - start_time
            if duration > 1:
                self.log.warn("Publishing analysis data took {duration:.3f} seconds", duration=duration)
            elif duration > 0.5:
                self.log.info("Publishing analysis data took {duration:.3f} seconds", duration=duration)
            else:
                self.log.debug("Publishing analysis data took {duration:.3f} seconds", duration=duration)

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

    def getManifest(self):
        manifest = []
        for mclass, module in self.modules.iteritems():
            manifest.append((mclass, module.getName()))
        return manifest

    def getData(self, mclass=None, *args):
        if mclass is None:
            allData = {}
            for clz, module in self.modules.iteritems():
                allData[clz] = module.getData()
            return _make_data_message(allData)
        elif mclass in self.modules:
            d = self.modules[mclass].getData(*args)
            return _make_data_message(d)
        else:
            raise RuntimeError("No such analysis module: {}".format(mclass))

    def getCars(self):
        return map(lambda car: (car.race_num, car.driver_name()), self.data_centre.cars)

    def reset(self):
        self.data_centre.reset()


class Analysis(object):
    def __init__(self, data_centre):
        self.data_centre = data_centre

    def getName(self):
        raise NotImplementedError

    def getData(self):
        raise NotImplementedError


def _fullname(ttype):
    module = ttype.__module__
    if module is None or module == str.__class__.__module__:
        return ttype.__name__
    return module + '.' + ttype.__name__
