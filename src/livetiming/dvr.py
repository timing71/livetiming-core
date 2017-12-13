from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import SubscribeOptions
from livetiming import load_env
from livetiming.network import authenticatedService, Realm, RPC, Channel,\
    MessageClass, Message
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import os
from livetiming.recording import TimingRecorder
from lzstring import LZString
import simplejson


def create_dvr_session(dvr):
    class DVRSession(ApplicationSession):
        @inlineCallbacks
        def onJoin(self, _):
            dvr.log.info("DVR session ready")
            yield self.subscribe(dvr.handle_service_message, RPC.STATE_PUBLISH.format(''), options=SubscribeOptions(match=u'prefix', details_arg='details'))
            yield self.subscribe(dvr.handle_control_message, Channel.CONTROL)

        def onDisconnect(self):
            dvr.log.info("Disconnected from live timing service")

    return authenticatedService(DVRSession)


class DVR(object):
    def __init__(self):
        self.log = Logger()
        self._in_progress_recordings = {}

    def start(self):
        session_class = create_dvr_session(self)
        router = unicode(os.environ["LIVETIMING_ROUTER"])
        runner = ApplicationRunner(url=router, realm=Realm.TIMING)
        runner.run(session_class, auto_reconnect=True)
        self.log.info("DVR terminated.")

    def handle_service_message(self, message, details=None):
        if details and details.topic:
            msg = Message.parse(message)
            service_uuid = details.topic.split('.')[-1]

            if msg.msgClass == MessageClass.SERVICE_DATA:
                self._store_data_frame(service_uuid, msg.payload)
            elif msg.msgClass == MessageClass.SERVICE_DATA_COMPRESSED:
                state = simplejson.loads(LZString().decompressFromUTF16(msg.payload))
                self._store_data_frame(service_uuid, state)

    def handle_control_message(self, message):
        msg = Message.parse(message)
        if msg.msgClass == MessageClass.SERVICE_REGISTRATION:
            self._store_manifest(msg.payload)

    def _get_recording(self, service_uuid):
        if service_uuid not in self._in_progress_recordings:
            rec_file = "{}.zip".format(service_uuid)

            if os.path.isfile(rec_file):
                self.log.info("Resuming existing recording for UUID {uuid}", uuid=service_uuid)
            else:
                self.log.info("Starting new recording for UUID {uuid}", uuid=service_uuid)
            self._in_progress_recordings[service_uuid] = TimingRecorder(rec_file)

        return self._in_progress_recordings[service_uuid]

    def _store_manifest(self, manifest):
        self._get_recording(manifest['uuid']).writeManifest(manifest)

    def _store_data_frame(self, uuid, frame):
        self._get_recording(uuid).writeState(frame)


def main():
    load_env()
    Logger().info("Starting DVR service...")
    dvr = DVR()
    dvr.start()


if __name__ == '__main__':
    main()
