from abc import ABC, abstractmethod
from autobahn.twisted.component import run
from autobahn.wamp.types import PublishOptions
from livetiming import make_component, VERSION
from livetiming.analysis import Analyser
from livetiming.messages import FlagChangeMessage, CarPitMessage,\
    DriverChangeMessage, FastLapMessage
from livetiming.network import Channel, Message, MessageClass, RPC
from livetiming.racing import Stat
from livetiming.recording import TimingRecorder
from lzstring import LZString
from treq.client import HTTPClient
from twisted.internet import reactor
from twisted.internet.task import LoopingCall, deferLater
from twisted.internet.threads import deferToThread
from twisted.logger import Logger
from twisted.web import client
from uuid import uuid4

from .session import create_service_session
from .standalone import create_standalone_session

import copy
import os
import sentry_sdk
import simplejson
import sys
import time


class AbstractService(ABC):
    '''
    All timing services must derive from this abstract base class.

    You probably want to extend BaseService, which provides some
    default implementations for some of the methods below, rather than
    extend this class directly.
    '''

    auto_poll = True
    '''
    If `auto_poll` is `True` then this service will have
    _updateAndPublishRaceState called every getPollInterval() seconds.
    If `False` it's expected that the service will call
    _updateAndPublishRaceState itself when there is new data to be
    published.
    '''

    attribution = None
    '''

    '''

    @abstractmethod
    def getName(self):
        '''
        Must be implemented by subclasses to return the string used as
        a name for this service.

        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when
        the value changes, or the change will not propagate to clients.
        '''
        pass

    @abstractmethod
    def getDefaultDescription(self):
        '''
        Must be implemented by subclasses to return the string used as
        a description, unless one has been provided at runtime with -d.

        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when
        the value changes, or the change will not propagate to clients.
        '''
        pass

    @abstractmethod
    def getColumnSpec(self):
        '''
        Must be implemented by subclasses to return a list of Stat
        objects representing the list of available columns to display.

        If the value returned by this function is not constant then the
        service will probably want to call self.publishManifest() when
        the value changes, or the change will not propagate to clients.
        '''
        pass

    @abstractmethod
    def getRaceState(self):
        '''
        Must be implemented by subclasses to return an dict containing
        two keys:

        {
          'cars': [...list of car stat lists...],
          'state': { ... dict of state values ... }
        }

        Each entry in 'cars' should be a list of values matching the
        column spec. All times should be in decimal seconds - this
        includes sector and lap times.

        Keys in 'state' can include:
         - flagState (livetiming.racing.FlagState.<flag>.name.lower())
         - timeElapsed (in seconds)
         - timeRemain (in seconds)
         - lapsRemain (integer)
         - trackData (list of formatted strings to display as track
           data)

        No filtering is performed; all values herein will be sent to
        clients. This means they need to be serializable e.g. plain
        Python types, not objects.
        '''
        pass

    @abstractmethod
    def getTrackDataSpec(self):
        '''
        Must be implemented by subclasses to provide a list of strings
        that are the keys of the key/value pairs of track data to
        display.
        '''
        pass

    @abstractmethod
    def getPollInterval(self):
        '''
        Must be implemented by subclasses to specify the interval, in
        seconds, at which self.getRaceState() will be called and the
        latest state published to clients.
        '''
        pass

    @abstractmethod
    def getExtraMessageGenerators(self):
        '''
        Must be implemented by subclasses to provide a list of
        additional message generators (subclasses of
        `livetiming.messages.TimingMessage`) to be used when generating
        messages for this service.

        The default set of generators cannot be overridden; those
        generators are written to be safe and silent in the event that
        their required data is unavailable.
        '''
        pass

    @abstractmethod
    def getVersion(self):
        '''
        Must be implemented by subclasses to provide a string version
        number for the plugin.
        '''


class ManifestPublisher(object):
    '''
    Rate-limits calls to publishManifest to at most once per second.
    '''
    def __init__(self):
        super().__init__()
        self._last_deferred = None

    def publishManifest(self):
        if not self._last_deferred or self._last_deferred.called:
            self._last_deferred = deferLater(
                reactor,
                1,
                self._publish_manifest_actual
            )

    def _publish_manifest_actual(self):
        manifest = self._createServiceRegistration()
        self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, manifest).serialise())
        if self.recorder:
            self.recorder.writeManifest(manifest)


class DuePublisher(object):
    '''
    Disables auto_poll and instead will call _updateAndPublishRaceState
    at most once per second and at least once every
    max_publish_interval seconds.
    '''
    auto_poll = False
    max_publish_interval = 60

    def __init__(self, *args, **kwargs):
        super(DuePublisher, self).__init__(*args, **kwargs)
        self._due_publish = False
        self._last_publish_time = time.time()

    def set_due_publish(self):
        '''
        Set a flag indicating that new data is available to be published.

        No matter how frequently this method is called, data will be
        published according to the constraints set by this class.
        '''
        self._due_publish = True

    def start(self):
        def maybePublish():
            now = time.time()
            if self._due_publish or (now - self._last_publish_time) > self.max_publish_interval:
                self.log.debug('Publishing race state update')
                self._updateAndPublishRaceState()
                self._due_publish = False
                self._last_publish_time = time.time()

        self.log.info('Polling for publishable state updates.')
        LoopingCall(maybePublish).start(1)

        super(DuePublisher, self).start()


class BaseService(AbstractService, ManifestPublisher):
    '''
    This class serves as the base class for all Service implementations.
    It contains some sensible default implementations for some of the
    AbstractService interface, as well as startup and state update
    logic including message generation and calling the analysis
    subsystem.
    '''
    log = Logger()

    def __init__(self, args, extra_args={}):
        super().__init__()
        self.args = args
        self.uuid = os.path.splitext(os.path.basename(self.args.initial_state))[0] if self.args.initial_state is not None else uuid4().hex
        self.state = self._getInitialState()
        if self.args.recording_file is not None:
            self.recorder = TimingRecorder(self.args.recording_file)
        else:
            self.recorder = None

        if self.args.disable_analysis:
            self.analyser = None
        else:
            self.analyser = Analyser(
                self.uuid,
                self.publish,
                interval=self.getPollInterval()
            )
        self._publish = None

        with sentry_sdk.configure_scope() as scope:
            scope.set_tag('uuid', self.uuid)
            scope.set_tag('service_name', self._getServiceClass())

        self.http_client = HTTPClient(client.Agent(reactor))

    def set_publish(self, func):
        '''
        Set the function used by this service to publish state.
        This is called from ServiceSession when a connection is made
        to the live timing network.
        '''
        self._publish = func

    def publish(self, *args, **kwargs):
        if self._publish:
            self._publish(*args, **kwargs)
            return True
        else:
            self.log.debug("Call to publish with no publish function set!")
            return False

    def start(self):
        '''
        Creates an ServiceSession component for this service, connects
        to the live timing network, and starts any looping calls
        required to run the service.

        This method calls autobahn.twisted.component#run and so will
        block until the session terminates (usually as a result of an
        interrupt or an error).
        '''

        if self.auto_poll:
            updater = LoopingCall(self._updateAndPublishRaceState)
            updater.start(self.getPollInterval(), False)
            self.log.info("Race state updates started")

        if self.analyser and not self.args.no_write_state:
            def saveAsync():
                self.log.debug("Saving data centre state")
                return deferToThread(self.analyser.save_data_centre)
            LoopingCall(saveAsync).start(60)
            LoopingCall(self.analyser._publish_pending).start(60)
            self.analyser.publish_all()

        if 'LIVETIMING_ROUTER' not in os.environ:
            self.log.info('LIVETIMING_ROUTER not set, forcing standalone mode.')
            self.args.standalone = True

        if self.args.standalone:
            def report_port(port):
                print(
                    'Standalone server for uuid:{} listening on port:{}'.format(self.uuid, port),
                    file=sys.stderr
                )
            session = create_standalone_session(self, report_port)
            session.run()
        else:
            session_class = create_service_session(self)
            component = make_component(session_class)
            run(component, log_level='debug' if self.args.debug else 'info')

        self.log.info("Service terminated.")

    #################################################
    # These methods MAY be overridden by subclasses #
    #################################################

    def getTrackDataSpec(self):
        return []

    def getPollInterval(self):
        return 10

    def getExtraMessageGenerators(self):
        return []

    ######################################################
    # These methods MUST NOT be overridden by subclasses #
    ######################################################

    def _getInitialState(self):
        if self.args.initial_state is not None:
            with open(self.args.initial_state, 'r') as stateFile:
                try:
                    return simplejson.load(stateFile)
                except Exception as e:
                    self.log.failure("Exception trying to load saved state: {log_failure}")
                    sentry_sdk.capture_exception(e)
        return {
            "messages": [],
            "session": {
                "flagState": "green",
                "timeElapsed": 0,
                "timeRemain": 0},
            "cars": []
        }

    def _saveState(self):
        if not self.args.no_write_state:
            self.log.debug("Saving state of {}".format(self.uuid))

            state_dir = os.environ.get("LIVETIMING_STATE_DIR", os.getcwd())
            if not os.path.exists(state_dir):
                os.mkdir(state_dir)

            filepath = os.path.join(
                state_dir,
                "{}.json".format(self.uuid)
            )

            with open(filepath, 'w') as stateFile:
                try:
                    simplejson.dump(self.state, stateFile)
                except Exception as e:
                    self.log.failure("Exception while saving state: {log_failure}")
                    sentry_sdk.capture_exception(e)
            if self.recorder:
                self.recorder.writeState(self.state)

    def _createServiceRegistration(self):
        colspec = [s.value if isinstance(s, Stat) else s for s in self.getColumnSpec()]
        manifest = {
            "uuid": self.uuid,
            "name": self.getName(),
            "serviceClass": self._getServiceClass(),
            "description": self._getDescription(),
            "colSpec": colspec,
            "trackDataSpec": self.getTrackDataSpec(),
            "pollInterval": self.getPollInterval() or 1,
            "hasAnalysis": not self.args.disable_analysis,
            "hidden": self.args.hidden,
            "livetimingVersion": {
                'core': VERSION,
                'plugin': self.getVersion()
            }
        }

        if self.attribution:
            manifest['source'] = self.attribution
        else:
            self.log.warn('No attribution specified for {service}', service=manifest['serviceClass'])

        if self.args.do_not_record:
            manifest['doNotRecord'] = True

        return manifest

    def _getServiceClass(self):
        if self.args.masquerade:
            return self.args.masquerade

        # Return the final segment of the module path.
        # e.g. pluginbase._internalspace._sp1bab772cdae6d12afa062a7e7632e890.timeservice_nl
        return self.__module__.split('.')[-1]

    def _getDescription(self):
        if self.args.description is not None:
            return self.args.description
        return self.getDefaultDescription()

    def _updateRaceState(self):
        try:
            newState = self.getRaceState()
            new_messages = self._createMessages(self.state, newState)
            self.state["highlight"] = list(set([m[4] for m in new_messages if len(m) >= 5]))  # list -> set to uniquify, -> list again to serialise
            self.state["messages"] = (new_messages + self.state["messages"])[0:100]
            self.state["cars"] = copy.deepcopy(newState["cars"])
            self.state["session"] = copy.deepcopy(newState["session"])

            if self.analyser:
                reactor.callInThread(  # This could take some time, let's be sure to not block the reactor
                    self.analyser.receiveStateUpdate,
                    newState,
                    self.getColumnSpec(),
                    new_messages=new_messages
                )

            self._saveState()
        except Exception as e:
            self.log.failure("Exception while updating race state: {log_failure}")
            sentry_sdk.capture_exception(e)

    def _updateAndPublishRaceState(self):
        self.log.debug("Updating and publishing timing data for {}".format(self.uuid))
        self._updateRaceState()
        self.publish(
            RPC.STATE_PUBLISH.format(self.uuid),
            Message(
                MessageClass.SERVICE_DATA_COMPRESSED,
                LZString().compressToUTF16(simplejson.dumps(self.state)),
                retain=True
            ).serialise(),
            options=PublishOptions(retain=True)
        )

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
            try:
                messages += mg.process(oldState, newState)
            except Exception as e:
                self.log.failure("Exception while generating messages: {log_failure}")
                sentry_sdk.capture_exception(e)

        return messages

    def _requestCurrentState(self):
        return simplejson.loads(simplejson.dumps(self.state))

    def _requestCurrentAnalysisState(self):
        if self.analyser:
            return self.analyser.get_current_state()
        return None

    def onControlMessage(self, message):
        msg = Message.parse(message)
        self.log.debug("Received message {msg}", msg=msg)
        if msg.msgClass == MessageClass.INITIALISE_DIRECTORY:
            self.log.info("Publishing manifest on request of directory service.")
            self.publishManifest()
