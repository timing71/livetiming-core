from datetime import datetime
from livetiming.racing import Stat, FlagStatus
from livetiming.service import Service as lt_service, MultiLineFetcher

import argparse
import simplejson
import re
import urllib


def parse_extra_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", help="livetiming.net series URL path")

    return parser.parse_args(args)


FILE_PACKET_REGEX = re.compile(r"(?:ltFilePKT = ')([^']+)")
TITLE_REGEX = re.compile(r"(?:ltBaseTitle = ')(.*)';")
COL_LABEL_REGEX = re.compile(r"(?:ltColLabel = )([^;]+)")


def getBaseData(series):
    url = "http://livetiming.net/{}".format(series)
    rq = urllib.request.Request(url)
    rq.add_header("User-Agent", "livetiming")
    raw = urllib.request.urlopen(rq).read()

    response = raw.decode('utf-8')

    used_columns = []
    for colset in re.findall(r"(?:'800' : )(.+)(?:,)", response):
        for c in simplejson.loads(colset):
            if int(c) not in used_columns:
                used_columns.append(int(c))

    available_cols = simplejson.loads(COL_LABEL_REGEX.search(response).group(1))

    return {
        "filename": FILE_PACKET_REGEX.search(response).group(1),
        "available_cols": available_cols,
        "used_cols": used_columns,
        "title": TITLE_REGEX.search(response).group(1).encode('utf-8').decode('unicode_escape')
    }


def ident(i):
    return i


def mapState(raw):
    mapping = {
        "active": "RUN",
        "in pit": "PIT",
        "missedseve": "?"
    }
    if raw.lower() in mapping:
        return mapping[raw.lower()]
    return raw


def parseFlags(raw):
    flags = []

    while len(raw) > 0 and raw[-1] in ["/", "*", "+"]:
        flags.append(raw[-1])
        raw = raw[0:-1]

    if "/" in flags:
        flag = "sb"
    elif "+" in flags:
        flag = "pb"
    else:
        flag = ""

    return (flag, raw)


def parseLaptime(raw):
    flag, raw = parseFlags(raw)

    try:
        ttime = datetime.strptime(raw, "%M:%S.%f")
        timeval = (60 * ttime.minute) + ttime.second + (ttime.microsecond / 1000000.0)
    except ValueError:
        timeval = ''

    return (timeval, flag)


def parseSectorTime(raw):
    flag, raw = parseFlags(raw)
    try:
        timeval = float(raw)
    except ValueError:
        timeval = raw

    return (timeval, flag)


def parseSessionTime(formattedTime):
    try:
        ttime = datetime.strptime(formattedTime, "%H:%M:%S")
        return (60 * 60 * ttime.hour) + (60 * ttime.minute) + ttime.second
    except ValueError:
        try:
            ttime = datetime.strptime(formattedTime, "%M:%S")
            return (60 * ttime.minute) + ttime.second
        except ValueError:
            return 0


def stripFlags(raw):
    _, raw = parseFlags(raw)
    return raw


def parseDelta(raw):
    if raw == '---' or raw == '--.----':
        return ''
    try:
        return float(raw)
    except ValueError:
        return raw


def dashToBlank(raw):
    if raw == '---':
        return ''
    return raw


def mapSessionFlag(raw):
    mapping = {
        'C': FlagStatus.CHEQUERED,
        'G': FlagStatus.GREEN,
        'Y': FlagStatus.YELLOW,
        'R': FlagStatus.RED,
        'W': FlagStatus.WHITE
    }
    if raw in mapping:
        return mapping[raw].name.lower()
    return "none"


# ["P","No","Name","Laps","LapTime","FL","FTime","Diff","Gap","Pits","LPit","Led","ST","Status","Speed","FSpeed","Elapsed","CLS","PFLapTime","MPL","CRank","CFLap","CFLapTime","CFastSpeed","CDiff","CGap","PIC","P2P","Make","Nat","Team","Sponsor","Residence","Chassis","Engine","Tire","Points"]

FULL_COL_SPEC = [
    # Stat, label used at livetiming.net, mapping function
    (Stat.NUM, "No", ident),
    (Stat.STATE, "Status", mapState),
    (Stat.CLASS, "CLS", ident),
    (Stat.POS_IN_CLASS, "PIC", ident),
    (Stat.DRIVER, "Name", ident),
    (Stat.CAR, "Make", ident),
    (Stat.CAR, "Chassis", ident),
    (Stat.TEAM, "Team", ident),
    (Stat.LAPS, "Laps", dashToBlank),
    (Stat.TYRE, "Tire", ident),
    (Stat.PUSH_TO_PASS, "P2P", ident),
    (Stat.GAP, "Diff", parseDelta),
    (Stat.INT, "Gap", parseDelta),
    (Stat.S1, "S1", parseSectorTime),
    (Stat.S1, "Section 1", parseSectorTime),
    (Stat.S2, "S2", parseSectorTime),
    (Stat.S2, "Section 2", parseSectorTime),
    (Stat.S3, "S3", parseSectorTime),
    (Stat.S3, "Section 3", parseSectorTime),
    (Stat.S4, "Section 4", parseSectorTime),
    (Stat.LAST_LAP, "LapTime", parseLaptime),
    (Stat.SPEED, "Spd", stripFlags),
    (Stat.BEST_LAP, "FTime", parseLaptime)
]


class Service(lt_service):
    auto_poll = False

    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)

        self.myArgs = parse_extra_args(extra_args)

        self.colSpec = []
        self.colMapping = []
        self.name = "livetiming.net"
        self.description = ""

        self.packet = None

        self._configure(getBaseData(self.getSeries()))

        f = MultiLineFetcher(
            bytes(
                "http://livetiming.net/{}/LoadPKT.asp?filename={}".format(
                    self.getSeries(),
                    self.filename
                ),
                'utf-8'
            ),
            self.handlePacket,
            5)
        f.start()

    def getSeries(self):
        return self.myArgs.series

    def _configure(self, data):
        cols_available = data["available_cols"]
        cols_used = data["used_cols"]
        for stat, label, mapFunc in FULL_COL_SPEC:
            idx = cols_available.index(label) if label in cols_available else None
            if idx and idx in cols_used:
                self.colSpec.append(stat)
                self.colMapping.append((idx, mapFunc))
        self.name = data["title"]
        self.filename = data["filename"]

    def getColumnSpec(self):
        return self.colSpec

    def getName(self):
        return self.name

    def getDefaultDescription(self):
        return self.description

    def handlePacket(self, packet):
        self.packet = list(map(lambda p: p.decode('utf-8'), packet))

        header = self.packet[0][2:].split("|")
        newDesc = header[0]
        if newDesc != self.description:
            self.description = newDesc
            self.publishManifest()
        self._updateAndPublishRaceState()

    def getRaceState(self):
        cars = []

        session = {}

        if self.packet:
            header = self.packet[0][2:].split("|")
            car_rows = [c for c in [[c.strip() for c in s.split("|")] for s in self.packet[1:]] if c[0] != "" and c[0] != "<end>"]
            for car_row in car_rows:
                car = []
                for idx, mapFunc in self.colMapping:
                    car.append(mapFunc(car_row[idx]))
                cars.append(car)

            session['flagState'] = mapSessionFlag(header[5])
            session['timeElapsed'] = parseSessionTime(header[4])
            session['timeRemain'] = parseSessionTime(header[8])
            if len(header[1]) > 0 and header[1][0] == 'R':  # In race only
                session['lapsRemain'] = header[9]

        return {"cars": cars, "session": session}
