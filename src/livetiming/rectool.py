import argparse
import datetime
import os
import re
import simplejson
import tempfile
import zipfile


# http://stackoverflow.com/a/25739108/11643
def updateZip(zipname, filename, data):
    # generate a temp file
    tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(zipname))
    os.close(tmpfd)

    # create a temp copy of the archive without filename
    with zipfile.ZipFile(zipname, 'r') as zin:
        with zipfile.ZipFile(tmpname, 'w') as zout:
            zout.comment = zin.comment  # preserve the comment
            seen_filenames = []
            for item in zin.infolist():
                if item.filename != filename and item.filename not in seen_filenames:
                    zout.writestr(item, zin.read(item.filename))
                    seen_filenames.append(item.filename)

    # replace with the temp archive
    os.remove(zipname)
    os.rename(tmpname, zipname)

    # now add filename with its new data
    with zipfile.ZipFile(zipname, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, data)


class RecordingFile(object):
    def __init__(self, filename):
        self.filename = filename
        self.iframes = []
        self.keyframes = []
        with zipfile.ZipFile(filename, 'r', zipfile.ZIP_DEFLATED) as z:
            maxFrame = 0
            for frame in z.namelist():
                m = re.match("([0-9]{5})(i?)", frame)
                if m:
                    val = int(m.group(1))
                    if m.group(2):  # it's an iframe
                        self.iframes.append(val)
                    else:
                        self.keyframes.append(val)
                    maxFrame = max(val, maxFrame)
            self.duration = maxFrame
            self.manifest = simplejson.load(z.open("manifest.json", 'r'))
        self.frames = len(self.iframes) + len(self.keyframes)

    def save_manifest(self):
        updateZip(self.filename, "manifest.json", simplejson.dumps(self.manifest))


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
    print "Start time: {}".format(datetime.datetime.fromtimestamp(f.manifest['startTime']))


ACTIONS = {
    'inspect': inspect,
    'describe': describe
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
