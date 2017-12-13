from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import SubscribeOptions
from livetiming import load_env
from livetiming.network import authenticatedService, Realm, RPC, Channel,\
    MessageClass, Message
from livetiming.recording import TimingRecorder
from lzstring import LZString
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import os
import shutil
import simplejson
import time
from twisted.internet.task import LoopingCall


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


RECORDING_TIMEOUT = 5 * 60  # 5 minutes


class DVR(object):
    def __init__(self):
        self.log = Logger()
        self._in_progress_recordings = {}
        self.IN_PROGRESS_DIR = os.getenv('LIVETIMING_RECORDINGS_TEMP_DIR', './recordings-temp')
        self.FINISHED_DIR = os.getenv('LIVETIMING_RECORDINGS_DIR', './recordings')

    def start(self):
        if not os.path.isdir(self.IN_PROGRESS_DIR):
            os.mkdir(self.IN_PROGRESS_DIR)

        if not os.path.isdir(self.FINISHED_DIR):
            os.mkdir(self.FINISHED_DIR)

        finished_scan = LoopingCall(self._scan_for_finished_recordings)
        finished_scan.start(RECORDING_TIMEOUT)

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
            rec_file = os.path.join(self.IN_PROGRESS_DIR, "{}.zip".format(service_uuid))

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

    def _scan_for_finished_recordings(self):
        threshold = int(time.time()) - RECORDING_TIMEOUT

        finished_recordings = []

        for service_uuid, recording in self._in_progress_recordings.iteritems():
            if recording.latest_frame and recording.latest_frame < threshold:
                finished_recordings.append(service_uuid)

        for uuid in finished_recordings:
            self._finish_recording(uuid)

        self.log.info("DVR state: {in_progress} in progress, {finished} finished recordings", in_progress=len(self._in_progress_recordings), finished=len(finished_recordings))

    def _finish_recording(self, uuid):
        self.log.info("Finishing recording for UUID {uuid}", uuid=uuid)
        self._in_progress_recordings.pop(uuid)

        dest = os.path.join(self.FINISHED_DIR, "{}.zip".format(uuid))

        shutil.move(
            os.path.join(self.IN_PROGRESS_DIR, "{}.zip".format(uuid)),
            dest
        )

        os.chmod(dest, 0664)


def main():
    load_env()
    Logger().info("Starting DVR service...")
    dvr = DVR()
    dvr.start()


if __name__ == '__main__':
    main()
