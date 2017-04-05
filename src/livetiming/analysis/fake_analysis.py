#!/usr/bin/env python
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.analysis import Analyser
from livetiming.recording import RecordingFile
from livetiming.network import Realm, RPC, Channel, Message, MessageClass,\
    authenticatedService
from livetiming.racing import Stat
from livetiming import load_env
from livetiming.analysis.driver import StintLength
from livetiming.analysis.pits import EnduranceStopAnalysis
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

import os
import sys
import time
from twisted.internet.threads import deferToThread
from twisted.internet.task import LoopingCall


@authenticatedService
class FakeAnalysis(ApplicationSession):

    def __init__(self, config):
        ApplicationSession.__init__(self, config)

        recFile = sys.argv[1]

        self.a = Analyser("TEST", self.publish, [StintLength, EnduranceStopAnalysis], publish=False)

        self.rec = RecordingFile(recFile)

        self.manifest = self.rec.manifest
        self.manifest['uuid'] = "TEST"
        self.manifest['name'] = "System Test"
        self.manifest['description'] = "system under test"

    @inlineCallbacks
    def onJoin(self, details):
        print "Joined"

        def true():
            return True
        yield self.register(true, RPC.LIVENESS_CHECK.format("TEST"))
        yield self.register(self.a.getManifest, RPC.REQUEST_ANALYSIS_MANIFEST.format("TEST"))
        yield self.register(self.a.getData, RPC.REQUEST_ANALYSIS_DATA.format("TEST"))
        yield self.register(self.a.getCars, RPC.REQUEST_ANALYSIS_CAR_LIST.format("TEST"))
        yield self.publish(Channel.CONTROL, Message(MessageClass.SERVICE_REGISTRATION, self.manifest).serialise())

        print "All registered"
        pcs = Stat.parse_colspec(self.rec.manifest['colSpec'])

        def saveAsync():
            print "Saving data centre state"
            return deferToThread(lambda: self.a.save_data_centre())
        LoopingCall(saveAsync).start(60)

        def preprocess():
            start_time = time.time()
            for i in range(self.rec.frames + 1):
                newState = self.rec.getStateAt(i * int(self.manifest['pollInterval']))
                self.a.receiveStateUpdate(newState, pcs, self.rec.manifest['startTime'] + (i * int(self.manifest['pollInterval'])))
                print "{}/{} ({})".format(i, self.rec.frames, i / (time.time() - start_time))
                # time.sleep(4)
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
    runner.run(FakeAnalysis)


if __name__ == '__main__':
    main()
