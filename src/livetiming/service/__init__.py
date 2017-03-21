from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.analysis import Analyser
from livetiming.messages import FlagChangeMessage, CarPitMessage,\
    DriverChangeMessage, FastLapMessage
from livetiming.network import Channel, Message, MessageClass, Realm, RPC, authenticatedService
from livetiming.racing import Stat
from livetiming.recording import TimingRecorder
from lzstring import LZString
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from uuid import uuid4

import argparse
import copy
import os
import simplejson
import txaio
import urllib2


@authenticatedService
class Service(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.args = config.extra
        self.uuid = os.path.splitext(self.args["initial_state"])[0] if self.args["initial_state"] is not None else uuid4().hex
        self.state = self._getInitialState()
        if self.args["recording_file"] is not None:
            self.recorder = TimingRecorder(self.args["recording_file"])
        else:
            self.recorder = None
        self.analyser = Analyser(self.uuid, self.publish, self.getAnalysisModules())

    ###################################################
    # These methods MUST be implemented by subclasses #
    ###################################################

    def getName(self):
        '''
        Must be implemented by subclasses to return the string used as a
        name for this service.
        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when the
        value changes, or the change will not propagate to clients.
        '''
        raise NotImplementedError

    def getDefaultDescription(self):
        '''
        Must be implemented by subclasses to return the string used as a
        description, unless one has been provided at runtime with -d.
        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when the
        value changes, or the change will not propagate to clients.
        '''
        raise NotImplementedError

    def getColumnSpec(self):
        '''
        Must be implemented by subclasses to return a list of Stat objects
        representing the list of available columns to display.
        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when the
        value changes, or the change will not propagate to clients.
        '''
        raise NotImplementedError

    def getRaceState(self):
        '''
        Must be implemented by subclasses to return an dict containing two keys:
        {
          'cars': [...list of car stat lists...],
          'state': { ... dict of state values ... }
        }

        Each entry in 'cars' should be a list of values matching the column spec.
        All times should be in decimal seconds - this includes sector and lap times.

        Keys in 'state' can include:
         - flagState (livetiming.racing.FlagState.<flag>.name.lower())
         - timeElapsed (in seconds)
         - timeRemain (in seconds)
         - lapsRemain (integer)
         - trackData (list of formatted strings to display as track data)

        No filtering is performed; all values herein will be sent to clients.
        This means they need to be serializable e.g. plain Python types, not
        objects.
        '''
        raise NotImplementedError

    #################################################
    # These methods MAY be overridden by subclasses #
    #################################################

    def getTrackDataSpec(self):
        '''
        May be overridden by subclasses to provide a list of strings that are
        the keys of the key/value pairs of track data to display.
        Defaults to an empty list.
        '''
        return []

    def getPollInterval(self):
        '''
        May be overridden by clients to specify the interval, in seconds, at
        which self.getRaceState() will be called and the latest state published
        to clients.

        TODO: Push-based (websockety) services would be better served
        publishing updates directly and immediately rather than themselves
        being polled...
        '''
        return 10

    def getExtraMessageGenerators(self):
        '''
        May be overridden by subclasses to provide a list of additional message
        generators (subclasses of livetiming.messages.TimingMessage) to be used
        when generating messages for this service.

        The default set of generators cannot be overridden; those generators
        are written to be safe and silent in the event that their required data
        is unavailable.
        '''
        return []

    def getAnalysisModules(self):
        '''
        May be overridden by subclasses to provide a list of analysis modules
        (by class) for this service.
        '''
        return []

    ######################################################
    # These methods MUST NOT be overridden by subclasses #
    ######################################################

    def _getInitialState(self):
        if self.args["initial_state"] is not None:
            try:
                stateFile = open(self.args["initial_state"], 'r')
                return simplejson.load(stateFile)
            except Exception:
                self.log.failure("Exception trying to load saved state: {log_failure}")
            finally:
                stateFile.close()
        return {
            "messages": [],
            "session": {
                "flagState": "green",
                "timeElapsed": 0,
                "timeRemain": 0},
            "cars": []
        }

    def _saveState(self):
        self.log.debug("Saving state of {}".format(self.uuid))
        try:
            stateFile = open("{}.json".format(self.uuid), 'w')
            simplejson.dump(self.state, stateFile)
        except Exception:
            self.log.failure("Exception while saving state: {log_failure}")
        finally:
            stateFile.close()
        if self.recorder:
            self.recorder.writeState(self.state)

    def _createServiceRegistration(self):
        colspec = map(lambda s: s.value if isinstance(s, Stat) else s, self.getColumnSpec())
        return {
            "uuid": self.uuid,
            "name": self.getName(),
            "description": self._getDescription(),
            "colSpec": colspec,
            "trackDataSpec": self.getTrackDataSpec(),
            "pollInterval": self.getPollInterval(),
            "hasAnalysis": not not self.getAnalysisModules()
        }

    def _getDescription(self):
        if self.args['description'] is not None:
            return self.args['description']
        return self.getDefaultDescription()

    def _isAlive(self):
        return True

    def _updateRaceState(self):
        try:
            newState = self.getRaceState()
            self.state["messages"] = (self._createMessages(self.state, newState) + self.state["messages"])[0:100]
            self.state["cars"] = copy.deepcopy(newState["cars"])
            self.state["session"] = copy.deepcopy(newState["session"])

            self.analyser.receiveStateUpdate(newState, self.getColumnSpec())
            self._saveState()
        except Exception:
            self.log.failure("Exception while updating race state: {log_failure}")

    def _updateAndPublishRaceState(self):
        self.log.debug("Publishing timing data for {}".format(self.uuid))
        self._updateRaceState()
        self.publish(unicode(self.uuid), self._requestCurrentState())

    def _getMessageGenerators(self):
        return [
            FlagChangeMessage(),
            CarPitMessage(self.getColumnSpec()),
            DriverChangeMessage(self.getColumnSpec()),
            FastLapMessage(self.getColumnSpec()),
        ]

    def _createMessages(self, oldState, newState):
        # Messages are of the form [time, category, text, messageType]
        messages = []
        for mg in self._getMessageGenerators() + self.getExtraMessageGenerators():
            messages += mg.process(oldState, newState)
        return messages

    def _requestCurrentState(self):
        return Message(MessageClass.SERVICE_DATA_COMPRESSED, LZString().compressToUTF16(simplejson.dumps(self.state))).serialise()

    def publishManifest(self):
        self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self._createServiceRegistration()).serialise())
        if self.recorder:
            self.recorder.writeManifest(self._createServiceRegistration())

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready for service {}".format(self.uuid))
        yield self.register(self._isAlive, RPC.LIVENESS_CHECK.format(self.uuid))
        yield self.register(self._requestCurrentState, RPC.REQUEST_STATE.format(self.uuid))
        yield self.register(self.analyser.getManifest, RPC.REQUEST_ANALYSIS_MANIFEST.format(self.uuid))
        yield self.register(self.analyser.getData, RPC.REQUEST_ANALYSIS_DATA.format(self.uuid))
        yield self.subscribe(self.onControlMessage, Channel.CONTROL)
        self.log.info("Subscribed to control channel")
        yield self.publishManifest()
        self.log.info("Published init message")

        updater = LoopingCall(self._updateAndPublishRaceState)
        updater.start(self.getPollInterval())
        self.log.info("Service started")

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.info("Received message {}".format(msg))
        if msg.msgClass == MessageClass.INITIALISE_DIRECTORY:
            yield self.publishManifest()

    def onDisconnect(self):
        self.log.info("Disconnected from live timing service")
        if reactor.running:
            reactor.stop()


class Fetcher(object):
    log = Logger()

    def __init__(self, url, callback, interval):
        self.url = url
        self.callback = callback
        self.interval = interval

    def _run(self):
        if callable(self.url):
            url = self.url()
        else:
            url = self.url

        try:
            feed = urllib2.urlopen(url)
            if feed.getcode() == 200:
                self.callback(feed.read())
            else:
                self.log.warn("HTTP {} on url {}".format(feed.getcode(), url))
        except Exception:
            pass  # Bad data feed :(

    def start(self):
        self.loop = LoopingCall(self._run)
        self.loop.start(self.interval)


def JSONFetcher(url, callback, interval):
    return Fetcher(url, lambda j: callback(simplejson.loads(j)), interval)


def MultiLineFetcher(url, callback, interval):
    return Fetcher(url, lambda l: callback(l.splitlines()), interval)


def parse_args():
    parser = argparse.ArgumentParser(description='Run a Live Timing service.')

    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('-r', '--recording-file', nargs='?', help='File to record timing data to')
    parser.add_argument('-d', '--description', nargs='?', help='Service description')
    parser.add_argument('service_class', nargs='?', default='livetiming.service.Service', help='Class name of service to run')
    parser.add_argument('-v', '--verbose', action='store_true')

    return parser.parse_known_args()


def get_class(kls):
    parts = kls.split('.')
    module = ".".join(parts[:-1])
    m = __import__(module)
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


def service_name_from(srv):
    if srv.startswith("livetiming."):
        return srv
    return "livetiming.service.{}.Service".format(srv)


def main():
    router = unicode(os.environ["LIVETIMING_ROUTER"])

    args, extra_args = parse_args()

    extra = vars(args)
    extra['extra_args'] = extra_args

    service_class = get_class(service_name_from(args.service_class))
    Logger().info("Starting timing service {}...".format(service_class.__module__))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING, extra=extra)

    with open("{}.log".format(args.service_class), 'a', 0) as logFile:
        if not args.verbose:
            txaio.start_logging(out=logFile, level='info')
        runner.run(service_class)
        print "Service terminated."


if __name__ == '__main__':
    main()
