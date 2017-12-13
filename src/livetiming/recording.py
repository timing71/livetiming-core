from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming import load_env
from livetiming.network import RPC, Realm, authenticatedService, Message,\
    MessageClass, Channel
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

import dictdiffer
import os
import re
import simplejson
import time
import zipfile
import tempfile
import datetime


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

    # replace with the temp archive
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
        self.latest_frame = None

    def writeManifest(self, serviceRegistration):
        serviceRegistration["startTime"] = time.time()
        serviceRegistration["version"] = 1
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if "manifest.json" not in z.namelist():
                z.writestr("manifest.json", simplejson.dumps(serviceRegistration))
                return True
        updateZip(self.recordFile, "manifest.json", simplejson.dumps(serviceRegistration))

    def writeState(self, state):
        timestamp = int(time.time())
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if self.frames % INTRA_FRAMES == 0:  # Write a keyframe
                z.writestr("{:011d}.json".format(timestamp), simplejson.dumps(state))
            else:  # Write an intra-frame
                diff = self._diffState(state)
                z.writestr("{:011d}i.json".format(timestamp), simplejson.dumps(diff))
        self.frames += 1
        self.prevState = state.copy()
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
            'messages': messagesDiff
        }


class RecordingFile(object):
    def __init__(self, filename, force_compat=False):
        self.filename = filename
        self.iframes = []
        self.keyframes = []
        with zipfile.ZipFile(filename, 'r', zipfile.ZIP_DEFLATED) as z:
            self.manifest = simplejson.load(z.open("manifest.json", 'r'))

            if "version" not in self.manifest and not force_compat:
                raise Exception("Unknown / pre-v1 recording file, unsupported. Try rectool convert")
            if "version" in self.manifest and self.manifest['version'] != 1:
                raise Exception("Unknown recording file version {}, cannot continue".format(self.manifest['version']))

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
        'messages': (iframe['messages'] + initial['messages'])[0:100]
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
            fullPath = os.path.join(self.recordingDirectory, recFileName)
            recFile = RecordingFile(fullPath)
            manifest = recFile.augmentedManifest()
            manifest['filename'] = recFileName
            self.recordings[manifest['uuid']] = manifest
        self.publish(Channel.CONTROL, Message(MessageClass.RECORDING_LISTING, self.recordings).serialise())
        self.log.info("Directory scan completed, {count} recording{s} found", count=len(self.recordings), s='' if len(self.recordings) == 1 else 's')

    def listRecordings(self):
        return self.recordings


@authenticatedService
class RecordingsDirectory(ApplicationSession):
    @inlineCallbacks
    def onJoin(self, details):
        self.replayManager = ReplayManager(self.publish, "recordings/")
        yield self.register(self.replayManager.listRecordings, RPC.RECORDING_LISTING)
        self.log.info("Registered recording listing RPC")

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    load_env()
    Logger().info("Starting recording directory service...")
    router = unicode(os.environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(RecordingsDirectory)


if __name__ == '__main__':
    main()
