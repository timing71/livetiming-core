from datetime import datetime, timedelta
from twisted.logger import Logger

import dictdiffer
import re
import simplejson
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
                for frame in z.namelist():
                    m = re.match("([0-9]{5})i?", frame)
                    if m:
                        val = int(m.group(1))
                        maxFrame = max(val, maxFrame)
                self.log.info("Found existing recording, starting recording at time + {}".format(maxFrame))
                self.startTime = self.startTime - timedelta(seconds=maxFrame)
        except Exception as e:
            print e
        self.frames = 0
        self.prevState = {'cars': [], 'session': {}, 'messages': []}

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
