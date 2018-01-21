from autobahn.wamp import auth
from enum import Enum

import os
import time


class Realm:
    TIMING = u'timing'


class Channel:
    CONTROL = u'livetiming.control'
    DIRECTORY = u'livetiming.directory'
    SCHEDULER = u'livetiming.scheduler'


class RPC:
    DIRECTORY_LISTING = u"livetiming.directory.listServices"
    RECORDING_LISTING = u"livetiming.directory.listRecordings"
    SCHEDULE_LISTING = u"livetiming.schedule.list"
    LIVENESS_CHECK = u"livetiming.service.isAlive.{}"
    REQUEST_STATE = u"livetiming.service.requestState.{}"
    REQUEST_ANALYSIS_MANIFEST = u"livetiming.service.requestAnalysisManifest.{}"
    REQUEST_ANALYSIS_DATA = u"livetiming.service.requestAnalysisData.{}"
    REQUEST_ANALYSIS_CAR_LIST = u"livetiming.service.requestAnalysisCarList.{}"
    STATE_PUBLISH = u"livetiming.service.{}"


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

    def __init__(self, msgClass, payload=None, date=None):
        self.msgClass = msgClass
        self.payload = payload
        self.date = date if date else int(time.time() * 1000)

    def serialise(self):
        return {
            'msgClass': self.msgClass.value,
            'date': self.date,
            'payload': self.payload
        }

    @staticmethod
    def parse(rawMsg):
        return Message(MessageClass(rawMsg['msgClass']), rawMsg['payload'], int(rawMsg['date'] / 1000) if 'date' in rawMsg else None)

    def __str__(self):
        return u"<Message class={0} payload={1}>".format(self.msgClass, self.payload)


def authenticatedService(clazz):
    '''
    Decorator for ApplicationSessions that require authentication using LIVETIMING_SHARED_SECRET.
    '''
    def onConnect(self):
        self.log.info("Client session connected. Starting WAMP-CRA authentication on realm '{}' as user '{}' ..".format(self.config.realm, "services"))
        self.join(self.config.realm, [u"wampcra", u"anonymous"], u"services")

    def onChallenge(self, challenge):
        user_secret = os.environ.get('LIVETIMING_SHARED_SECRET', None)
        if challenge.method == u"wampcra":
            self.log.debug("WAMP-CRA challenge received: {}".format(challenge))

            if u'salt' in challenge.extra:
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
