from datetime import datetime
from twisted.logger import Logger


class TimingRecorder(object):
    def __init__(self, recordFile):
        self.recordFile = recordFile
        self.startTime = datetime.now()
        self.frames = 0
        self.log = Logger()

    def writeState(self, state):
        self.log.info("STUB TimingRecorder.writeState()")
