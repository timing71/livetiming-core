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
RECORDING_DURATION_THRESHOLD = 10 * 60  # recordings shorter than 10 minutes are thrown away


def dedupe(filename):
    f, ext = os.path.splitext(filename)

    d = 0
    while os.path.exists(filename):
        d += 1
        filename = "{}_{}{}".format(f, d, ext)
    return filename


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
                self._store_data_frame(service_uuid, state, msg.date)

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
        uuid = manifest['uuid']
        rec = self._get_recording(uuid)
        if rec.manifest:
            # We've received a new manifest for a recording that already has one
            # If the title or description are different, then start a new recording file
            if rec.manifest['name'] != manifest['name'] or rec.manifest['description'] != manifest['description']:
                self.log.info(
                    "Detected manifest changes for {uuid} ({old_name} - {old_desc} to {new_name} - {new_desc}). Triggering new recording.",
                    uuid=uuid,
                    old_name=rec.manifest['name'],
                    old_desc=rec.manifest['description'],
                    new_name=manifest['name'],
                    new_desc=manifest['description']
                )
                self._finish_recording(uuid)
                rec = self._get_recording(uuid)

        rec.writeManifest(manifest)

    def _store_data_frame(self, uuid, frame, date):
        self._get_recording(uuid).writeState(frame, date)

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
        recording = self._in_progress_recordings.pop(uuid)

        src = recording.recordFile
        if recording.duration < RECORDING_DURATION_THRESHOLD:
            self.log.warn(
                "Recording for UUID {uuid} of duration {duration}s is less than threshold ({threshold}s), deleting recording file.",
                uuid=uuid,
                duration=recording.duration,
                threshold=RECORDING_DURATION_THRESHOLD
            )
            os.remove(src)
        else:
            dest = dedupe(os.path.join(self.FINISHED_DIR, "{}.zip".format(uuid)))

            shutil.move(
                src,
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
