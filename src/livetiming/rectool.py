import argparse
import datetime
import re
import simplejson
import zipfile


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


def inspect(args):
    f = RecordingFile(args.recfile)
    print "##########"
    print f.manifest['description']
    print "##########"
    print "Service: {} ({})".format(f.manifest['name'], f.manifest['uuid'])
    print "{} frames ({}k/{}i), {} duration".format(f.frames, len(f.keyframes), len(f.iframes), f.duration)
    print "Start time: {}".format(datetime.datetime.fromtimestamp(f.manifest['startTime']))


ACTIONS = {
    'inspect': inspect
}


def _parse_args():
    parser = argparse.ArgumentParser(description='Tool for manipulating Live Timing recordings.')
    parser.add_argument('action', choices=ACTIONS.keys(), help='Action to perform')
    parser.add_argument('recfile', help='Recording file to use')
    return parser.parse_args()


def main():
    args = _parse_args()
    if args.action in ACTIONS.keys():
        ACTIONS[args.action](args)
    else:
        # argparse should prevent us from getting here
        print "Unrecognised action: {}".format(args.action)
        print "Available actions: {}".format(ACTIONS.keys())


if __name__ == '__main__':
    main()
