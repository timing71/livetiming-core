#!/usr/bin/env python
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from datetime import datetime
from livetiming.analysis import Analyser
from livetiming.recording import RecordingFile
from livetiming.network import Realm, RPC, Channel, Message, MessageClass,\
    authenticatedService
from livetiming.racing import Stat
from livetiming import load_env
from livetiming.analysis.data import *
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

import os
import sys
import time
import txaio
from twisted.internet.threads import deferToThread
from twisted.internet.task import LoopingCall


@authenticatedService
class FakeAnalysis(ApplicationSession):

    def __init__(self, config):
        ApplicationSession.__init__(self, config)

        recFile = sys.argv[1]

        self.rec = RecordingFile(recFile)

        self.manifest = self.rec.manifest
        self.manifest['uuid'] = "TEST"
        self.manifest['name'] = "System Test"
        self.manifest['description'] = "system under test"
        self.manifest['hidden'] = True

    @inlineCallbacks
    def onJoin(self, details):
        print "Joined"

        self.a = Analyser("TEST", self.publish)

        def true():
            return True
        yield self.register(true, RPC.LIVENESS_CHECK.format("TEST"))
        yield self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.manifest).serialise())

        print "All registered"
        pcs = Stat.parse_colspec(self.rec.manifest['colSpec'])

        def preprocess():
            start_time = time.time()
            frames = sorted(self.rec.keyframes + self.rec.iframes)
            frame_count = len(frames)

            for idx, frame in enumerate(frames):
                newState = self.rec.getStateAtTimestamp(frame)
                self.a.receiveStateUpdate(newState, pcs, frame)

                now = time.time()
                current_fps = float(idx) / (now - start_time)
                eta = datetime.fromtimestamp(start_time + (frame_count / current_fps) if current_fps > 0 else 0)
                print "{}/{} ({:.2%}) {:.3f}fps eta:{}".format(idx, frame_count, float(idx) / frame_count, current_fps, eta.strftime("%H:%M:%S"))
                # time.sleep(1)
            stop_time = time.time()
            print "Processed {} frames in {}s == {:.3f} frames/s".format(self.rec.frames, stop_time - start_time, self.rec.frames / (stop_time - start_time))

        reactor.callInThread(preprocess)

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    load_env()
    router = unicode(os.environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    txaio.start_logging(level='debug')
    runner.run(FakeAnalysis)


if __name__ == '__main__':
    main()
