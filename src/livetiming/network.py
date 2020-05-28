from autobahn.wamp import auth
from enum import Enum

import os
import time


class Realm:
    TIMING = 'timing'


class Channel:
    CONTROL = 'livetiming.control'
    DIRECTORY = 'livetiming.directory'
    SCHEDULER = 'livetiming.scheduler'
    RECORDING = 'livetiming.replay'


class RPC:
    ANALYSIS_PUBLISH = "livetiming.analysis/{}/{}"
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
        wamp_auth_id = os.environ.get('LIVETIMING_AUTH_ID', 'services')
        self.log.info(
            "Client session connected. Starting WAMP-CRA authentication on realm '{realm}' with authid '{authid}' ..",
            realm=self.config.realm,
            authid=wamp_auth_id
        )
        self.join(self.config.realm, ["wampcra", "anonymous"], wamp_auth_id)

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
