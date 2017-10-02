from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.twisted.websocket import WebSocketClientFactory
from autobahn.wamp.types import RegisterOptions
from livetiming import load_env, sentry
from livetiming.analysis import Analyser
from livetiming.messages import FlagChangeMessage, CarPitMessage,\
    DriverChangeMessage, FastLapMessage
from livetiming.network import Channel, Message, MessageClass, Realm, RPC, authenticatedService
from livetiming.racing import Stat
from livetiming.recording import TimingRecorder
from lzstring import LZString
from simplejson.scanner import JSONDecodeError
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.task import LoopingCall
from twisted.internet.threads import deferToThread
from twisted.logger import Logger
from twisted.web import client
from uuid import uuid4

import argparse
import copy
import os
import simplejson
import txaio


sentry = sentry()

client.HTTPClientFactory.noisy = False


def create_service_session(service):
    class ServiceSession(ApplicationSession):

        def _isAlive(self):
            return True

        @inlineCallbacks
        def onJoin(self, details):
            service.log.info("Session ready for service {}".format(service.uuid))
            service.set_publish(self.publish)

            register_opts = RegisterOptions(force_reregister=True)

            yield self.register(self._isAlive, RPC.LIVENESS_CHECK.format(service.uuid), register_opts)
            yield self.register(service._requestCurrentState, RPC.REQUEST_STATE.format(service.uuid), register_opts)
            yield self.register(service.analyser.getManifest, RPC.REQUEST_ANALYSIS_MANIFEST.format(service.uuid), register_opts)
            yield self.register(service.analyser.getData, RPC.REQUEST_ANALYSIS_DATA.format(service.uuid), register_opts)
            yield self.register(service.analyser.getCars, RPC.REQUEST_ANALYSIS_CAR_LIST.format(service.uuid), register_opts)
            yield self.subscribe(service.onControlMessage, Channel.CONTROL)
            self.log.info("Subscribed to control channel")
            yield service.publishManifest()
            self.log.info("Published init message")
            service._updateAndPublishRaceState()

        def onLeave(self, details):
            super(ServiceSession, self).onLeave(details)
            service.log.info("Left WAMP session: {details}", details=details)

        def onDisconnect(self):
            service.log.info("Disconnected from live timing service")
            service.set_publish(None)

    return authenticatedService(ServiceSession)


class Service(object):
    log = Logger()

    def __init__(self, args, extra_args={}):
        sentry.context.activate()
        self.sentry = sentry
        self.args = args
        self.uuid = os.path.splitext(os.path.basename(self.args.initial_state))[0] if self.args.initial_state is not None else uuid4().hex
        self.state = self._getInitialState()
        if self.args.recording_file is not None:
            self.recorder = TimingRecorder(self.args.recording_file)
        else:
            self.recorder = None
        self.analyser = Analyser(self.uuid, self.publish, self.getAnalysisModules() if not args.disable_analysis else [])
        self._publish = None
        self.sentry.context.merge({
            'tags': {
                'uuid': self.uuid,
                'service_name': self.__module__
            }
        })

    def set_publish(self, func):
        self._publish = func

    def publish(self, *args):
        if self._publish:
            self._publish(*args)
        else:
            self.log.debug("Call to publish with no publish function set!")

    def start(self):
        session_class = create_service_session(self)
        router = unicode(os.environ["LIVETIMING_ROUTER"])
        runner = ApplicationRunner(url=router, realm=Realm.TIMING)

        if self.getPollInterval():
            updater = LoopingCall(self._updateAndPublishRaceState)
            updater.start(self.getPollInterval(), False)
            self.log.info("Race state updates started")

        if self.getAnalysisModules():
            def saveAsync():
                self.log.debug("Saving data centre state")
                return deferToThread(lambda: self.analyser.save_data_centre())
            LoopingCall(saveAsync).start(60)

        runner.run(session_class, auto_reconnect=True, log_level="debug" if self.args.debug else "info")
        self.log.info("Service terminated.")

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
        if self.args.initial_state is not None:
            with open(self.args.initial_state, 'r') as stateFile:
                try:
                    return simplejson.load(stateFile)
                except Exception:
                    self.log.failure("Exception trying to load saved state: {log_failure}")
                    sentry.captureException()
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

        filepath = os.path.join(
            os.environ.get("LIVETIMING_STATE_DIR", os.getcwd()),
            "{}.json".format(self.uuid)
        )

        with open(filepath, 'w') as stateFile:
            try:
                simplejson.dump(self.state, stateFile)
            except Exception:
                self.log.failure("Exception while saving state: {log_failure}")
                sentry.captureException()
        if self.recorder:
            self.recorder.writeState(self.state)

    def _createServiceRegistration(self):
        colspec = map(lambda s: s.value if isinstance(s, Stat) else s, self.getColumnSpec())
        return {
            "uuid": self.uuid,
            "name": self.getName(),
            "serviceClass": self.__module__[19:],  # Everything after 'livetiming.service.'
            "description": self._getDescription(),
            "colSpec": colspec,
            "trackDataSpec": self.getTrackDataSpec(),
            "pollInterval": self.getPollInterval() or 1,
            "hasAnalysis": not (self.args.disable_analysis or not self.getAnalysisModules()),
            "hidden": self.args.hidden
        }

    def _getDescription(self):
        if self.args.description is not None:
            return self.args.description
        return self.getDefaultDescription()

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
            sentry.captureException()

    def _updateAndPublishRaceState(self):
        self.log.debug("Updating and publishing timing data for {}".format(self.uuid))
        self._updateRaceState()
        self.publish(RPC.STATE_PUBLISH.format(self.uuid), self._requestCurrentState())

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

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.debug("Received message {msg}", msg=msg)
        if msg.msgClass == MessageClass.INITIALISE_DIRECTORY:
            self.log.info("Publishing manifest on request of directory service.")
            self.publishManifest()


class Fetcher(object):
    log = Logger()

    def __init__(self, url, callback, interval):
        self.url = url
        self.callback = callback
        self.interval = interval

        self.backoff = 0
        self.running = False

    def _schedule(self, delay):
        if self.running:
            reactor.callLater(delay, self._run)

    def _defer(self):
        if callable(self.url):
            url = self.url()
        else:
            url = self.url

        try:
            return client.getPage(url)
        except Exception as e:
            self.log.failure("URL {url} returned error: {msg}", url=url, msg=str(e))
            raise

    def _run(self):
        def cb(data):
            self.backoff = 0
            self.callback(data)
            self._schedule(self.interval)

        def eb(fail):
            self.backoff += 1
            self.log.warn("{fail}. Trying again in {backoff} seconds", fail=fail.getErrorMessage(), backoff=self.interval * self.backoff)
            self._schedule(self.interval * self.backoff)

        deferred = self._defer()
        deferred.addCallback(cb)
        deferred.addErrback(eb)

    def start(self):
        self.running = True
        self._run()

    def stop(self):
        self.running = False


def JSONFetcher(url, callback, interval):
    def parse_then_callback(data):
        try:
            parsed_data = simplejson.loads(data)
            callback(parsed_data)
        except JSONDecodeError:
            Logger().failure("Error parsing JSON from source {url}: {log_failure}", url=url)
    return Fetcher(url, parse_then_callback, interval)


def MultiLineFetcher(url, callback, interval):
    return Fetcher(url, lambda l: callback(l.splitlines()), interval)


class ReconnectingWebSocketClientFactory(WebSocketClientFactory, ReconnectingClientFactory):
    log = Logger()

    def clientConnectionFailed(self, connector, reason):
        self.log.warn("Connection to upstream source failed! Reason: {reason}. Retrying...", reason=reason)
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        self.log.warn("Connection to upstream source lost! Reason: {reason}. Retrying...", reason=reason)
        self.retry(connector)


def parse_args():
    parser = argparse.ArgumentParser(description='Run a Live Timing service.')

    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('-r', '--recording-file', nargs='?', help='File to record timing data to')
    parser.add_argument('-d', '--description', nargs='?', help='Service description')
    parser.add_argument('service_class', nargs='?', default='livetiming.service.Service', help='Class name of service to run')
    parser.add_argument('-v', '--verbose', action='store_true', help='Log to stdout rather than a file')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--disable-analysis', action='store_true')
    parser.add_argument('-H', '--hidden', action='store_true', help='Hide this service from the UI except by UUID access')

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
    load_env()

    args, extra_args = parse_args()

    extra = vars(args)
    extra['extra_args'] = extra_args

    service_class = get_class(service_name_from(args.service_class))

    filepath = os.path.join(
        os.environ.get("LIVETIMING_LOG_DIR", os.getcwd()),
        "{}.log".format(args.service_class)
    )

    with open(filepath, 'a', 0) as logFile:
        level = "debug" if args.debug else "info"
        if not args.verbose:  # log to file, not stdout
            txaio.start_logging(out=logFile, level=level)

        Logger().info("Starting timing service {}...".format(service_class.__module__))
        service = service_class(args, extra_args)
        service.start()


if __name__ == '__main__':
    main()
