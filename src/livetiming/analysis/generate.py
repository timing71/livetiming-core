# Generate an analysis data dump from a recording file
import simplejson
import sys
import time

from datetime import datetime
from livetiming.analysis import Analyser
from livetiming.racing import Stat
from livetiming.recording import RecordingFile
from twisted.internet import defer


def main():
    recFile = sys.argv[1]
    rec = RecordingFile(recFile)
    manifest = rec.manifest

    a = Analyser("TEST", None)
    pcs = Stat.parse_colspec(manifest['colSpec'])

    start_time = time.time()
    frames = sorted(rec.keyframes + rec.iframes)
    frame_count = len(frames)

    data = {}
    for idx, frame in enumerate(frames):
        newState = rec.getStateAtTimestamp(frame)
        a.receiveStateUpdate(newState, pcs, frame)
        data['state'] = newState

        now = time.time()
        current_fps = float(idx) / (now - start_time)
        eta = datetime.fromtimestamp(start_time + (frame_count / current_fps) if current_fps > 0 else 0)
        print "{}/{} ({:.2%}) {:.3f}fps eta:{}".format(idx, frame_count, float(idx) / frame_count, current_fps, eta.strftime("%H:%M:%S"))

    stop_time = time.time()
    print "Processed {} frames in {}s == {:.3f} frames/s".format(rec.frames, stop_time - start_time, rec.frames / (stop_time - start_time))

    for key, module in a._modules.iteritems():
        data[key] = module.get_data(a.data_centre)

    with open('data.out.json', 'w') as outfile:
        simplejson.dump(data, outfile)

    print "Generation complete."


if __name__ == '__main__':
    main()
