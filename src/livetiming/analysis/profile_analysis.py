from livetiming.analysis import Analyser
from livetiming.recording import RecordingFile
import sys
from livetiming.racing import Stat
import time

recFile = sys.argv[1]

a = Analyser("TEST", lambda: False, [], publish=False)

rec = RecordingFile(recFile)

manifest = rec.manifest
manifest['uuid'] = "TEST"
manifest['name'] = "System Test"
manifest['description'] = "system under test"

pcs = Stat.parse_colspec(rec.manifest['colSpec'])

start_time = time.time()
for i in range(rec.frames + 1):
    newState = rec.getStateAt(i * int(manifest['pollInterval']))
    a.receiveStateUpdate(newState, pcs, rec.manifest['startTime'] + (i * int(manifest['pollInterval'])))
    print "{}/{} ({})".format(i, rec.frames, i / (time.time() - start_time))
    # time.sleep(4)
stop_time = time.time()
print "Processed {} frames in {}s == {:.3f} frames/s".format(rec.frames, stop_time - start_time, rec.frames / (stop_time - start_time))
