from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import PublishOptions
from livetiming import configure_sentry_twisted, load_env, sentry
from livetiming.analysis import Analyser
from livetiming.network import RPC, Realm, authenticatedService, Message,\
    MessageClass, Channel
from livetiming.racing import Stat
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

import datetime
import dictdiffer
import glob
import os
import re
import simplejson
import shutil
import sys
import tempfile
import time
import zipfile


INTRA_FRAMES = 10


# http://stackoverflow.com/a/25739108/11643
def updateZip(zipname, filename, data, new_filename=None, new_zipname=None):
    # generate a temp file
    tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(zipname))
    os.close(tmpfd)

    # create a temp copy of the archive without filename
    with zipfile.ZipFile(zipname, 'r') as zin:
        with zipfile.ZipFile(tmpname, 'w') as zout:
            zout.comment = zin.comment  # preserve the comment
            seen_filenames = []
            for item in zin.infolist():
                if item.filename != filename and item.filename not in seen_filenames:
                    zout.writestr(item, zin.read(item.filename))
                    seen_filenames.append(item.filename)

    # replace with the temp archive, preserving permissions
    shutil.copymode(zipname, tmpname)
    os.remove(zipname)
    os.rename(tmpname, new_zipname if new_zipname else zipname)

    # now add filename with its new data
    with zipfile.ZipFile(zipname, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(new_filename if new_filename else filename, data)


class TimingRecorder(object):
    def __init__(self, recordFile):
        self.recordFile = recordFile
        self.log = Logger()
        self.frames = 0
        self.prevState = {'cars': [], 'session': {}, 'messages': []}
        self.first_frame = None
        self.latest_frame = time.time()
        self.manifest = None

    def writeManifest(self, serviceRegistration):
        serviceRegistration["startTime"] = time.time()
        serviceRegistration["version"] = 1
        self.manifest = serviceRegistration
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if "manifest.json" not in z.namelist():
                z.writestr("manifest.json", simplejson.dumps(serviceRegistration))
                return True
        updateZip(self.recordFile, "manifest.json", simplejson.dumps(serviceRegistration))

    def writeState(self, state, timestamp=None):
        if not timestamp:
            timestamp = int(time.time())
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if self.frames % INTRA_FRAMES == 0:  # Write a keyframe
                z.writestr("{:011d}.json".format(timestamp), simplejson.dumps(state))
            else:  # Write an intra-frame
                diff = self._diffState(state)
                z.writestr("{:011d}i.json".format(timestamp), simplejson.dumps(diff))
        self.frames += 1
        self.prevState = state.copy()
        if not self.first_frame:
            self.first_frame = timestamp
        self.latest_frame = timestamp

    def _diffState(self, newState):
        carsDiff = dictdiffer.diff(self.prevState['cars'], newState['cars'])
        sessionDiff = dictdiffer.diff(self.prevState['session'], newState['session'])
        messagesDiff = []
        for newMsg in newState['messages']:
            if len(self.prevState['messages']) == 0 or newMsg[0] > self.prevState['messages'][0][0]:
                messagesDiff.append(newMsg)
        return {
            'cars': list(carsDiff),
            'session': list(sessionDiff),
            'messages': messagesDiff,
            'highlight': newState.get('highlight', [])
        }

    @property
    def duration(self):
        if self.first_frame and self.latest_frame:
            return self.latest_frame - self.first_frame
        return 0


class RecordingException(Exception):
    pass


class RecordingFile(object):
    def __init__(self, filename, force_compat=False):
        self.filename = filename
        self.iframes = []
        self.keyframes = []
        with zipfile.ZipFile(filename, 'r', zipfile.ZIP_DEFLATED) as z:
            try:
                self.manifest = simplejson.load(z.open("manifest.json", 'r'))
            except KeyError:
                raise RecordingException("File contains no manifest.json, this is not a usable recording.")

            if "version" not in self.manifest and not force_compat:
                raise RecordingException("Unknown / pre-v1 recording file, unsupported. Try rectool convert")
            if "version" in self.manifest and self.manifest['version'] != 1:
                raise RecordingException("Unknown recording file version {}, cannot continue".format(self.manifest['version']))

            minFrame = 999999999999999
            maxFrame = 0
            for frame in z.namelist():
                m = re.match("([0-9]{5,11})(i?)", frame)
                if m:
                    val = int(m.group(1))
                    if m.group(2):  # it's an iframe
                        self.iframes.append(val)
                    else:
                        self.keyframes.append(val)
                    maxFrame = max(val, maxFrame)
                    minFrame = min(val, minFrame)
            self.startTime = datetime.datetime.fromtimestamp(minFrame)
            self.manifest['startTime'] = minFrame
            self.duration = (datetime.datetime.fromtimestamp(maxFrame) - self.startTime).total_seconds()
        self.frames = len(self.iframes) + len(self.keyframes)

    def save_manifest(self):
        updateZip(self.filename, "manifest.json", simplejson.dumps(self.manifest))

    def getStateAt(self, interval):
        return self.getStateAtTimestamp(self.manifest['startTime'] + interval)

    def getStateAtTimestamp(self, timecode):
        mostRecentKeyframeIndex = max([frame for frame in self.keyframes if frame <= timecode] + [min(self.keyframes)])
        intraFrames = [frame for frame in self.iframes if frame <= timecode and frame > mostRecentKeyframeIndex]

        with zipfile.ZipFile(self.filename, 'r', zipfile.ZIP_DEFLATED) as z:
            state = simplejson.load(z.open("{:011d}.json".format(mostRecentKeyframeIndex)))
            for iframeIndex in intraFrames:
                iframe = simplejson.load(z.open("{:011d}i.json".format(iframeIndex)))
                state = applyIntraFrame(state, iframe)

            return state

    def augmentedManifest(self):
        man = self.manifest
        man['duration'] = self.duration
        return man


def applyIntraFrame(initial, iframe):
    return {
        'cars': dictdiffer.patch(iframe['cars'], initial['cars']),
        'session': dictdiffer.patch(iframe['session'], initial['session']),
        'messages': (iframe['messages'] + initial['messages'])[0:100],
        'highlight': iframe.get('highlight', [])
    }


class ReplayManager(object):
    def __init__(self, publish, recordingDirectory):
        self.log = Logger()
        self.recordingDirectory = recordingDirectory
        self.publish = publish
        self.recordings = {}
        self.scanTask = LoopingCall(self.scanDirectory)
        self.scanTask.start(300)

    def scanDirectory(self):
        (_, _, filenames) = os.walk(self.recordingDirectory).next()
        self.recordings = {}
        for recFileName in filenames:
            try:
                fullPath = os.path.join(self.recordingDirectory, recFileName)
                recFile = RecordingFile(fullPath)
                manifest = recFile.augmentedManifest()
                manifest['filename'] = recFileName
                self.recordings[manifest['uuid']] = manifest
            except RecordingException:
                self.log.warn("Not a valid recording file: {filename}", filename=fullPath)
        self.publish(Channel.RECORDING, Message(MessageClass.RECORDING_LISTING, self.recordings, retain=True).serialise(), options=PublishOptions(retain=True))
        self.log.info("Directory scan completed, {count} recording{s} found", count=len(self.recordings), s='' if len(self.recordings) == 1 else 's')


@authenticatedService
class RecordingsDirectory(ApplicationSession):
    def onJoin(self, details):
        self.replayManager = ReplayManager(self.publish, os.environ.get('LIVETIMING_RECORDINGS_DIR', './recordings'))
        self.replayManager.log.info("Recordings directory service ready")

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def update_recordings_index():
    load_env()
    sentry()

    recordings_dir = os.environ.get('LIVETIMING_RECORDINGS_DIR', './recordings')

    index_filename = os.path.join(recordings_dir, 'index.json')
    index = {}

    try:
        with open(index_filename, 'r') as index_file:
            index = simplejson.load(index_file)
    except IOError:
        pass

    os.chdir(recordings_dir)

    rec_files = glob.glob('*.zip')

    for extant in index.keys():
        filename = extant.replace(':', '_') + '.zip'
        if filename not in rec_files:
            print 'Removing deleted recording file {}'.format(filename)
            del index[extant]

    for rec_file in rec_files:
        uuid = rec_file.replace('_', ':', 1)[0:-4]
        if uuid not in index:
            try:
                r = RecordingFile(rec_file)
                manifest = r.augmentedManifest()
                index[uuid] = {
                    'description': manifest['description'],
                    'duration': manifest['duration'],
                    'filename': rec_file,
                    'hidden': manifest.get('hidden', False),
                    'name': manifest['name'],
                    'startTime': manifest['startTime'],
                    'uuid': manifest['uuid'],
                }
                print "Added {} (UUID {}) to index".format(rec_file, manifest['uuid'])
            except RecordingException:
                self.log.warn("Not a valid recording file: {filename}", filename=fullPath)
                continue

        analysis_filename = os.path.join(recordings_dir, '{}.json'.format(rec_file[0:-4]))

        if 'hasAnalysis' not in index[uuid]:
            if os.path.isfile(analysis_filename):
                index[uuid]['hasAnalysis'] = True
            else:
                print "Generating post-session analysis file for {}...".format(rec_file)
                try:
                    generate_analysis(rec_file, analysis_filename, True)
                    index[uuid]['hasAnalysis'] = True
                except Exception as e:
                    print e
                    index[uuid]['hasAnalysis'] = False

    with open(index_filename, 'w') as index_file:
        simplejson.dump(index, index_file, separators=(',', ':'))


def generate_analysis(rec_file, out_file, report_progress=False):
    rec = RecordingFile(rec_file)
    manifest = rec.augmentedManifest()

    a = Analyser(manifest['uuid'], None)
    pcs = Stat.parse_colspec(manifest['colSpec'])

    start_time = time.time()
    frames = sorted(rec.keyframes + rec.iframes)
    frame_count = len(frames)

    data = {}
    for idx, frame in enumerate(frames):
        newState = rec.getStateAtTimestamp(frame)
        a.receiveStateUpdate(newState, pcs, frame)
        data['state'] = newState

        if report_progress:
            now = time.time()
            current_fps = float(idx) / (now - start_time)
            eta = datetime.datetime.fromtimestamp(start_time + (frame_count / current_fps) if current_fps > 0 else 0)
            sys.stdout.write("\r{}/{} ({:.2%}) {:.3f}fps eta:{}".format(idx, frame_count, float(idx) / frame_count, current_fps, eta.strftime("%H:%M:%S")))
            sys.stdout.flush()

    if report_progress:
        print ""
        stop_time = time.time()
        print "Processed {} frames in {}s == {:.3f} frames/s".format(rec.frames, stop_time - start_time, rec.frames / (stop_time - start_time))

    for key, module in a._modules.iteritems():
        data[key] = module.get_data(a.data_centre)

    data['service'] = manifest

    with open(out_file, 'w') as outfile:
        simplejson.dump(data, outfile, separators=(',', ':'))

    if report_progress:
        print "Generation complete."


def main():
    load_env()
    configure_sentry_twisted()
    Logger().info("Starting recording directory service...")
    router = unicode(os.environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(RecordingsDirectory)


if __name__ == '__main__':
    main()
