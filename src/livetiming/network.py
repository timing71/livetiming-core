from autobahn.wamp import auth
from enum import Enum
from jsonschema import ValidationError
from jsonschema.validators import validator_for
from twisted.logger import Logger

import os
import simplejson
import time


_LOG = Logger()


class Realm:
    TIMING = 'timing'


class Channel:
    CONTROL = 'livetiming.control'
    DIRECTORY = 'livetiming.directory'
    SCHEDULER = 'livetiming.scheduler'
    RECORDING = 'livetiming.replay'


class RPC:
    DIRECTORY_LISTING = "livetiming.directory.listServices"
    RECORDING_LISTING = "livetiming.directory.listRecordings"
    SCHEDULE_LISTING = "livetiming.schedule.list"
    LIVENESS_CHECK = "livetiming.service.isAlive.{}"
    REQUEST_STATE = "livetiming.service.requestState.{}"
    REQUEST_ANALYSIS_MANIFEST = "livetiming.service.requestAnalysisManifest.{}"
    REQUEST_ANALYSIS_DATA = "livetiming.service.requestAnalysisData.{}"
    REQUEST_ANALYSIS_CAR_LIST = "livetiming.service.requestAnalysisCarList.{}"
    STATE_PUBLISH = "livetiming.service.{}"
    GET_DIRECTORY_LISTING = 'livetiming.directory.listServices'
    GET_RECORDINGS_PAGE = 'livetiming.recordings.page'
    GET_RECORDINGS_NAMES = 'livetiming.recordings.names'
    GET_RECORDINGS_MANIFEST = 'livetiming.recordings.manifest'
    UPDATE_RECORDING_MANIFEST = 'livetiming.recordings.updateManifest'


class MessageClass(Enum):
    INITIALISE_DIRECTORY = 1
    SERVICE_REGISTRATION = 2
    SERVICE_DEREGISTRATION = 3
    SERVICE_DATA = 4
    DIRECTORY_LISTING = 5
    SCHEDULE_LISTING = 6
    ANALYSIS_DATA = 7
    SERVICE_DATA_COMPRESSED = 8
    ANALYSIS_DATA_COMPRESSED = 9
    RECORDING_LISTING = 10


VALIDATOR_PATH = os.path.join(os.path.relpath(os.path.dirname(__file__)), 'schemas/')


def make_validator(schema_name):
    schema_file = os.path.join(VALIDATOR_PATH, schema_name)
    with open(schema_file, 'r') as sf:
        schema = simplejson.load(sf)
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        return validator_class(schema)


VALIDATORS = {
    MessageClass.SERVICE_DATA: make_validator('state.json'),
    MessageClass.SERVICE_REGISTRATION: make_validator('manifest.json')
}


class Message(object):

    def __init__(self, msgClass, payload=None, date=None, retain=False):
        self.msgClass = msgClass
        self.payload = payload
        self.date = date if date else int(time.time() * 1000)
        self.retain = retain

    def serialise(self):
        msg = {
            'msgClass': self.msgClass.value,
            'date': self.date,
            'payload': self.payload
        }
        if self.retain:
            msg['retain'] = True
        return msg

    def validate(self):
        validator = VALIDATORS.get(self.msgClass)
        if validator:
            try:
                validator.validate(simplejson.loads(simplejson.dumps(self.payload)))
                _LOG.debug('Message type {msgtype} passed schema validation', msgtype=self.msgClass.name)
            except ValidationError as e:
                _LOG.error('Message type {msgtype} failed validation: {e}', msgtype=self.msgClass.name, e=e)
                print(self.payload)
                raise e

    @staticmethod
    def parse(rawMsg):
        return Message(MessageClass(rawMsg['msgClass']), rawMsg['payload'], int(rawMsg['date'] / 1000) if 'date' in rawMsg else None)

    def __str__(self):
        return "<Message class={0} payload={1}>".format(self.msgClass, self.payload)


def authenticatedService(clazz):
    '''
    Decorator for ApplicationSessions that require authentication using LIVETIMING_SHARED_SECRET.
    '''
    def onConnect(self):
        self.log.info("Client session connected. Starting WAMP-CRA authentication on realm '{}' as user '{}' ..".format(self.config.realm, "services"))
        self.join(self.config.realm, ["wampcra", "anonymous"], "services")

    def onChallenge(self, challenge):
        user_secret = os.environ.get('LIVETIMING_SHARED_SECRET', None)
        if challenge.method == "wampcra":
            self.log.debug("WAMP-CRA challenge received: {}".format(challenge))

            if 'salt' in challenge.extra:
                # salted secret
                key = auth.derive_key(user_secret,
                                      challenge.extra['salt'],
                                      challenge.extra['iterations'],
                                      challenge.extra['keylen'])
            else:
                # plain, unsalted secret
                key = user_secret

            # compute signature for challenge, using the key
            signature = auth.compute_wcs(key, challenge.extra['challenge'])

            # return the signature to the router for verification
            return signature

        else:
            raise Exception("Invalid authmethod {}".format(challenge.method))
    clazz.onConnect = onConnect
    clazz.onChallenge = onChallenge
    return clazz
