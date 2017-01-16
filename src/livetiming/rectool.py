import argparse
import os
import shutil
import simplejson
import tempfile
import zipfile

from livetiming.recording import RecordingFile


def describe(args, extras):
    f = RecordingFile(args.recfile)
    new_description = ' '.join(extras)
    f.manifest['description'] = new_description
    f.save_manifest()
    print "Set description to '{}'".format(new_description)


def inspect(args, extras):
    f = RecordingFile(args.recfile)
    print "##########"
    print f.manifest['description']
    print "##########"
    print "Service: {} ({})".format(f.manifest['name'], f.manifest['uuid'])
    print "{} frames ({}k/{}i), {} duration".format(f.frames, len(f.keyframes), len(f.iframes), f.duration)
    print "Start time: {}".format(f.startTime)


def convert(args, extras):
    orig = RecordingFile(args.recfile, force_compat=True)
    startTime = orig.manifest['startTime']

    tempdir = tempfile.mkdtemp(suffix=".rectool-convert")

    with zipfile.ZipFile(args.recfile, 'r', zipfile.ZIP_DEFLATED) as z:
        z.extractall(tempdir)

    with zipfile.ZipFile("conv_{}".format(args.recfile), 'w', zipfile.ZIP_DEFLATED) as z:
        for frame in orig.keyframes:
            print "{} => {}".format(frame, int(startTime + frame))
            z.write(os.path.join(tempdir, "{:05d}.json".format(frame)), "{:011d}.json".format(int(startTime + frame)))
        for frame in orig.iframes:
            print "{}i => {}i".format(frame, int(startTime + frame))
            z.write(os.path.join(tempdir, "{:05d}i.json".format(frame)), "{:011d}i.json".format(int(startTime + frame)))
        orig.manifest['version'] = 1
        del orig.manifest['startTime']
        z.writestr("manifest.json", simplejson.dumps(orig.manifest))

    shutil.rmtree(tempdir)


ACTIONS = {
    'inspect': inspect,
    'describe': describe,
    'convert': convert
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
