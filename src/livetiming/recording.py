from datetime import datetime, timedelta
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

import dictdiffer
import os
import re
import simplejson
import time
import zipfile


INTRA_FRAMES = 10


class TimingRecorder(object):
    def __init__(self, recordFile):
        self.recordFile = recordFile
        self.startTime = datetime.now()
        self.log = Logger()
        try:
            with zipfile.ZipFile(self.recordFile, 'r', zipfile.ZIP_DEFLATED) as z:
                maxFrame = 0
                names = z.namelist()
                if "manifest.json" in names:
                    manifest = simplejson.load(z.open("manifest.json", 'r'))
                    self.startTime = datetime.utcfromtimestamp(manifest['startTime'])
                else:
                    for frame in names:
                        m = re.match("([0-9]{5})i?", frame)
                        if m:
                            val = int(m.group(1))
                            maxFrame = max(val, maxFrame)
                    self.log.info("Found existing recording with no manifest, starting recording at time + {}".format(maxFrame))
                    self.startTime = self.startTime - timedelta(seconds=maxFrame)
        except Exception:
            pass
        self.frames = 0
        self.prevState = {'cars': [], 'session': {}, 'messages': []}

    def writeManifest(self, serviceRegistration):
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if "manifest.json" not in z.namelist():
                serviceRegistration["startTime"] = time.time()
                z.writestr("manifest.json", simplejson.dumps(serviceRegistration))
            else:
                self.log.info("Not overwriting existing manifest.")

    def writeState(self, state):
        timeDelta = (datetime.now() - self.startTime).total_seconds()
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            if self.frames % INTRA_FRAMES == 0:  # Write a keyframe
                z.writestr("{:05d}.json".format(int(timeDelta)), simplejson.dumps(state))
            else:  # Write an intra-frame
                diff = self._diffState(state)
                z.writestr("{:05d}i.json".format(int(timeDelta)), simplejson.dumps(diff))
        self.frames += 1
        self.prevState = state.copy()

    def _diffState(self, newState):
        carsDiff = dictdiffer.diff(self.prevState['cars'], newState['cars'])
        sessionDiff = dictdiffer.diff(self.prevState['session'], newState['session'])
        messagesDiff = []
        for newMsg in newState['messages']:
            if newMsg[0] > self.prevState['messages'][0][0]:
                messagesDiff.append(newMsg)
        return {
            'cars': list(carsDiff),
            'session': list(sessionDiff),
            'messages': messagesDiff
        }


class TimingReplayer(object):
    def __init__(self, recordFile):
        self.recordFile = recordFile
        self.iframes = []
        self.keyframes = []
        with zipfile.ZipFile(self.recordFile, 'r', zipfile.ZIP_DEFLATED) as z:
            maxFrame = 0
            for frame in z.namelist():
                m = re.match("([0-9]{5})(i?)", frame)
                if m:
                    val = int(m.group(1))
                    if m.group(2):  # it's an iframe
                        self.iframes.append(val)
                    else:
                        self.keyframes.append(val)
                    maxFrame = max(val, maxFrame)
            self.duration = maxFrame
            self.manifest = simplejson.load(z.open("manifest.json", 'r'))
        self.frames = len(self.iframes) + len(self.keyframes)

    def getStateAt(self, timecode):
        mostRecentKeyframeIndex = max([frame for frame in self.keyframes if frame <= timecode] + [min(self.keyframes)])
        intraFrames = [frame for frame in self.iframes if frame <= timecode and frame > mostRecentKeyframeIndex]

        with zipfile.ZipFile(self.recordFile, 'r', zipfile.ZIP_DEFLATED) as z:
            state = simplejson.load(z.open("{:05d}.json".format(mostRecentKeyframeIndex)))
            for iframeIndex in intraFrames:
                iframe = simplejson.load(z.open("{:05d}i.json".format(iframeIndex)))
                state = applyIntraFrame(state, iframe)

            return state


def applyIntraFrame(initial, iframe):
    return {
        'cars': dictdiffer.patch(iframe['cars'], initial['cars']),
        'session': dictdiffer.patch(iframe['session'], initial['session']),
        'messages': (iframe['messages'] + initial['messages'])[0:100]
    }


class ReplayManager(object):
    def __init__(self, directory):
        self.directory = directory
        self.recordings = {}
        self.scanTask = LoopingCall(self.scanDirectory)
        self.scanTask.start(300)

    def scanDirectory(self):
        (_, _, filenames) = os.walk(self.directory).next()
        self.recordings = {}
        for recFile in filenames:
            fullPath = os.path.join(self.directory, recFile)
            with zipfile.ZipFile(fullPath, 'r', zipfile.ZIP_DEFLATED) as z:
                manifest = simplejson.load(z.open("manifest.json", 'r'))
                self.recordings[manifest['uuid']] = (manifest, fullPath)

    def listRecordings(self):
        # Strip filenames out of listings that we return.
        return [v[0] for v in self.recordings.values()]
