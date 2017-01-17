import argparse
import dictdiffer
import os
import shutil
import simplejson
import tempfile
import time
import zipfile

from contextlib import contextmanager
from livetiming.recording import RecordingFile


@contextmanager
def temp_directory(suffix=""):
    td = tempfile.mkdtemp(suffix=suffix)
    try:
        yield td
    finally:
        shutil.rmtree(td)


def manifest_set(args, extras):
    if len(extras) != 2:
        raise Exception("Usage: rectool set <key> <value>")
    f = RecordingFile(args.recfile)
    f.manifest[extras[0]] = extras[1]
    f.save_manifest()


def inspect(args, extras):
    f = RecordingFile(args.recfile)
    print "##########"
    print f.manifest['description']
    print "##########"
    print "Service: {} ({})".format(f.manifest['name'], f.manifest['uuid'])
    print "{} frames ({}k/{}i), {} duration".format(f.frames, len(f.keyframes), len(f.iframes), f.duration)
    print "Start time: {}".format(f.startTime)
    print "Full manifest:"
    print simplejson.dumps(f.manifest, indent="  ")


def convert(args, extras):
    orig = RecordingFile(args.recfile, force_compat=True)
    startTime = orig.manifest['startTime']

    outfile = "{}{}_conv{}".format(os.path.dirname(args.recfile), *os.path.splitext(os.path.basename(args.recfile)))

    with temp_directory(suffix=".rectool-convert") as tempdir:

        with zipfile.ZipFile(args.recfile, 'r', zipfile.ZIP_DEFLATED) as z:
            z.extractall(tempdir)

            if not startTime or startTime < 60:
                firstKeyframe = min(orig.keyframes)
                info = z.getinfo("{:05d}.json".format(firstKeyframe))
                startTime = time.mktime(info.date_time + (0, 0, 0)) + firstKeyframe
                print "Start time not available, inferring from first keyframe as {}".format(startTime)

        with zipfile.ZipFile(outfile, 'w', zipfile.ZIP_DEFLATED) as z:
            for frame in orig.keyframes:
                print "{} => {}".format(frame, int(startTime + frame))
                z.write(os.path.join(tempdir, "{:05d}.json".format(frame)), "{:011d}.json".format(int(startTime + frame)))
            for frame in orig.iframes:
                print "{}i => {}i".format(frame, int(startTime + frame))
                z.write(os.path.join(tempdir, "{:05d}i.json".format(frame)), "{:011d}i.json".format(int(startTime + frame)))
            orig.manifest['version'] = 1
            del orig.manifest['startTime']
            z.writestr("manifest.json", simplejson.dumps(orig.manifest))


def clip(args, extras):
    orig = RecordingFile(args.recfile)
    startTime = orig.manifest['startTime']
    outfile = "{}{}_clip{}".format(os.path.dirname(args.recfile), *os.path.splitext(os.path.basename(args.recfile)))

    clipStart = False
    clipEnd = False
    if len(extras) >= 1:
        clipStart = int(extras[0][1:]) if extras[0][0] == "@" else int(extras[0]) + startTime
    if len(extras) >= 2:
        clipEnd = int(extras[1][1:]) if extras[1][0] == "@" else int(extras[1]) + startTime

    def shouldBeCopied(ts):
        return (not clipStart or ts >= clipStart) and (not clipEnd or ts < clipEnd)

    with temp_directory(".rectool-clip") as tempdir:

        with zipfile.ZipFile(args.recfile, 'r', zipfile.ZIP_DEFLATED) as z:
            z.extractall(tempdir)

        with zipfile.ZipFile(outfile, 'w', zipfile.ZIP_DEFLATED) as z:
            if clipStart not in orig.keyframes:
                z.writestr("{:011d}.json".format(clipStart), simplejson.dumps(orig.getStateAtTimestamp(clipStart)))
            for frame in orig.keyframes:
                if shouldBeCopied(frame):
                    z.write(os.path.join(tempdir, "{:011d}.json".format(frame)), "{:011d}.json".format(frame))
            for frame in orig.iframes:
                if shouldBeCopied(frame):
                    z.write(os.path.join(tempdir, "{:011d}i.json".format(frame)), "{:011d}i.json".format(frame))
            z.writestr("manifest.json", simplejson.dumps(orig.manifest))


def scan(args, extras):
    r = RecordingFile(args.recfile)
    startTime = r.manifest['startTime']
    interval = r.manifest['pollInterval'] if 'pollInterval' in r.manifest else 1
    print "First frame: {}".format(startTime)
    initialState = r.getStateAt(startTime)
    curTime = startTime

    foundSessionChange = False
    foundMessageChange = False
    foundCarsChange = False

    while curTime < startTime + r.duration:
        nowState = r.getStateAt(curTime)
        sessionDiffs = list(dictdiffer.diff(initialState['session'], nowState['session'])) if not foundSessionChange else []
        messageDiffs = list(dictdiffer.diff(initialState['messages'], nowState['messages'])) if not foundMessageChange else []
        carDiffs = list(dictdiffer.diff(initialState['cars'], nowState['cars'])) if not foundCarsChange else []
        if not foundSessionChange and len(sessionDiffs) > 0:
            print "First session change at {} (@{})".format(curTime - startTime, curTime)
            foundSessionChange = True
            print list(sessionDiffs)
        if not foundMessageChange and len(messageDiffs) > 0:
            print "First message change at {} (@{})".format(curTime - startTime, curTime)
            print list(messageDiffs)
            foundMessageChange = True
        if not foundCarsChange and len(carDiffs) > 0:
            print "First car change at {} (@{})".format(curTime - startTime, curTime)
            print list(carDiffs)
            foundCarsChange = True
        if foundCarsChange and foundMessageChange and foundSessionChange:
            break
        curTime += interval


def show(args, extras):
    r = RecordingFile(args.recfile)
    idx = extras[0]
    if idx[0] == "@":
        print r.getStateAtTimestamp(int(idx[1:]))
    else:
        print r.getStateAt(int(idx))


ACTIONS = {
    'inspect': inspect,
    'set': manifest_set,
    'convert': convert,
    'scan': scan,
    'show': show,
    'clip': clip
}


def _parse_args():
    parser = argparse.ArgumentParser(description='Tool for manipulating Live Timing recordings.')
    parser.add_argument('action', choices=ACTIONS.keys(), help='Action to perform')
    parser.add_argument('recfile', help='Recording file to use')
    return parser.parse_known_args()


def main():
    args, extras = _parse_args()
    if args.action in ACTIONS.keys():
        ACTIONS[args.action](args, extras)
    else:
        # argparse should prevent us from getting here
        print "Unrecognised action: {}".format(args.action)
        print "Available actions: {}".format(ACTIONS.keys())


if __name__ == '__main__':
    main()
