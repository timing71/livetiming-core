#!/usr/bin/env python
from autobahn.twisted.component import Component, run
from autobahn.twisted.wamp import ApplicationSession
from autobahn.twisted.websocket import WampWebSocketClientFactory
from autobahn.wamp.types import PublishOptions
from datetime import datetime
from livetiming.analysis import Analyser
from livetiming.recording import extract_recording
from livetiming.network import Realm, RPC, Channel, Message, MessageClass,\
    authenticatedService
from livetiming.racing import Stat
from livetiming import load_env
from livetiming.analysis.data import *
from lzstring import LZString
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

import os
import shutil
import simplejson
import sys
import time
import txaio
from twisted.internet.threads import deferToThread
from twisted.internet.task import LoopingCall


TEST_UUID = 'TEST'


@authenticatedService
class FakeAnalysis(ApplicationSession):

    def __init__(self, config):
        ApplicationSession.__init__(self, config)

        recFile = sys.argv[1]

        self.rec = extract_recording(recFile)

        self.manifest = self.rec.manifest
        self.manifest['uuid'] = TEST_UUID
        self.manifest['name'] = "System Test"
        self.manifest['description'] = "system under test"
        self.manifest['hidden'] = True
        self.manifest['doNotRecord'] = True

        self.a = Analyser(TEST_UUID, self.publish, interval=20)

    @inlineCallbacks
    def onJoin(self, details):
        print "Joined"

        def true():
            return True
        yield self.register(true, RPC.LIVENESS_CHECK.format(TEST_UUID))
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
                if (idx % 100 == 0):
                    self.publish(
                        RPC.STATE_PUBLISH.format(TEST_UUID),
                        Message(MessageClass.SERVICE_DATA_COMPRESSED, LZString().compressToUTF16(simplejson.dumps(newState)), retain=True).serialise(),
                        options=PublishOptions(retain=True)
                    )

                now = time.time()
                current_fps = float(idx) / (now - start_time)
                eta = datetime.fromtimestamp(start_time + (frame_count / current_fps) if current_fps > 0 else 0)
                print "{}/{} ({:.2%}) {:.3f}fps eta:{}".format(idx, frame_count, float(idx) / frame_count, current_fps, eta.strftime("%H:%M:%S"))
                # time.sleep(0.1)
            stop_time = time.time()
            print "Processed {} frames in {}s == {:.3f} frames/s".format(self.rec.frames, stop_time - start_time, self.rec.frames / (stop_time - start_time))
            self.a.save_data_centre()
            # Republish all data at the end
            for key, module in self.a._modules.iteritems():
                self.a._publish_data(key, module.get_data(self.a.data_centre))

        reactor.callInThread(preprocess)

    def onDisconnect(self):
        self.log.info("Disconnected")


def main():
    load_env()
    router = unicode(os.environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))

    component = Component(
        realm=Realm.TIMING,
        session_factory=FakeAnalysis,
        transports=[
            {
                'url': router,
                'options': {
                    'autoFragmentSize': 1024 * 128
                }
            }
        ]
    )

    run(component, log_level='info')


if __name__ == '__main__':
    main()
