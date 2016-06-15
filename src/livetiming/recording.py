from datetime import datetime
from twisted.logger import Logger

import simplejson
import zipfile


class TimingRecorder(object):
    def __init__(self, recordFile):
        self.recordFile = recordFile
        self.startTime = datetime.now()
        self.frames = 0
        self.log = Logger()

    def writeState(self, state):
        timeDelta = (datetime.now() - self.startTime).total_seconds()
        with zipfile.ZipFile(self.recordFile, 'a', zipfile.ZIP_DEFLATED) as z:
            z.writestr("{:05d}.json".format(int(timeDelta)), simplejson.dumps(state))
        self.frames += 1
