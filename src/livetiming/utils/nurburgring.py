# -*- coding: utf-8 -*-
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from twisted.web import client
from twisted.web.client import Agent, BrowserLikePolicyForHTTPS, readBody
from twisted.web.http_headers import Headers
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface import implementer

import base64
import copy
import re
import simplejson


# Work around SSL certificate misconfiguration at GPSauge's end:
@implementer(IPolicyForHTTPS)
class OneHostnameWorkaroundPolicy(object):
    def __init__(self):
        self._normalPolicy = BrowserLikePolicyForHTTPS()

    def creatorForNetloc(self, hostname, port):
        if hostname == b"dev.apioverip.com":
            hostname = b"gpsoverip.com"
        return self._normalPolicy.creatorForNetloc(hostname, port)


agent = Agent(reactor, OneHostnameWorkaroundPolicy())


@inlineCallbacks
def getPage(url):
    resp = yield agent.request(b'GET', url)
    body = yield readBody(resp)

    returnValue(body)


OVER_IP_APP = 'IPHNGR24'  # or IPHADAC24H
MARSHAL_POST_ADDRESS_URL = 'https://www.apioverip.de/?action=list&module=geoobject&nozlib=1&overipapp={}&type=address'
MARSHAL_POST_ID_URL = 'https://www.apioverip.de/?action=list&module=rule&nozlib=1&overipapp={}'
ACTIVE_ZONES_URL = 'https://dev.apioverip.de/racing/rules/active?overipapp={}'
# TRACK_STATE_URL = 'https://www.apioverip.de/?action=getconfig&mode=single&module=racing&nozlib=1&overipapp={}&param=track_state'

TOKEN_SPLIT_REGEX = re.compile('^(?P<field>[a-z]+([0-9]+_)?)((?P<idx>[0-9]+)):=(?P<value>.*)?$')

MARSHAL_POST_LOCATIONS = {
    '1': 'Main straight',
    '2': 'Main straight',
    '2a': 'Main straight',
    '3': 'Main straight',
    '4': 'Haug-Haken (Turn 1)',
    '4a': 'Haug-Haken (Turn 1)',
    '5': 'Haug-Haken (Turn 1)',
    '6': 'Mercedes arena',
    '7': 'Mercedes arena',
    '8': 'Mercedes arena',
    '9': 'Mercedes arena',
    '10': 'Yokohama-S',
    '11': 'Yokohama-S',
    '12': 'Valvoline',
    '13': 'Valvoline',
    '13a': 'NLS shortcut',
    '14': 'Valvoline',
    '15': 'Valvoline',
    '16': 'Valvoline',
    '16a': 'Valvoline',
    '17': 'Ford',
    '18': 'Ford',
    '19': 'Ford',
    '20': 'Ford – Dunlop',
    '21': 'Ford – Dunlop',
    '22': 'Dunlop',
    '23': 'Dunlop',
    '24': 'Dunlop',
    '25': 'Dunlop',
    '25a': 'Dunlop',
    '26': 'Dunlop',
    '27': 'Schumacher S',
    '28': 'Schumacher S',
    '29': 'Schumacher S',
    '30': 'Schumacher S',
    '31': 'Ravenol',
    '32': 'Ravenol',
    '33': 'Ravenol',
    '33a': 'Ravenol',
    '34': 'Bilstein',
    '35': 'Bilstein',
    '36': 'Bilstein',
    '37': 'Bilstein',
    '38': 'Bilstein',
    '39': 'Advan Arch',
    '40': 'Advan Arch',
    '40a': 'Advan Arch',
    '41': 'Advan Arch',
    '42': 'Veedol chicane',
    '42a': 'Veedol chicane',
    '42b': 'Veedol chicane',
    '42c': 'Veedol chicane',
    '43': 'Veedol chicane',
    '44': 'Jaguar',
    '45': 'Jaguar',
    '46': 'GP loop',
    '47': 'Main straight',
    '48': 'Main straight',
    '49': 'Pit lane',
    '50': 'Main straight',
    '60': 'Nordschliefe transition',
    '61': 'Nordschliefe transition',
    '62': 'Nordschliefe transition',
    '63': 'Hatzenbach approach',
    '64': 'Hatzenbach approach',
    '65': 'Hatzenbach',
    '66': 'Hatzenbach',
    '67': 'Hatzenbach',
    '68': 'Hatzenbach',
    '69': 'Hatzenbach',
    '70': 'Hatzenbach',
    '71': 'Hocheichen',
    '72': 'Hocheichen',
    '73': 'Hocheichen',
    '74': 'Hocheichen',
    '75': 'Hocheichen',
    '76': 'Quiddelbacher Höhe',
    '77': 'Quiddelbacher Höhe',
    '78': 'Quiddelbacher Höhe',
    '79': 'Quiddelbacher Höhe',
    '80': 'Flugplatz',
    '81': 'Flugplatz',
    '82': 'Schwedenkreuz 1',
    '83': 'Schwedenkreuz 1',
    '84': 'Schwedenkreuz 1',
    '85': 'Schwedenkreuz 2',
    '86': 'Schwedenkreuz 2',
    '87': 'Schwedenkreuz 2',
    '88': 'Aremberg',
    '89': 'Aremberg',
    '90': 'Aremberg',
    '91': 'Aremberg',
    '92': 'Aremberg',
    '92a': 'Aremberg',
    '93': 'Aremberg',
    '94': 'Fuchsröhre',
    '95': 'Fuchsröhre',
    '96': 'Fuchsröhre',
    '97': 'Fuchsröhre',
    '98': 'Fuchsröhre',
    '98a': 'Fuchsröhre',
    '99': 'Adenauer Forst',
    '100': 'Adenauer Forst',
    '100a': 'Metzgesfeld',
    '101': 'Metzgesfeld',
    '102': 'Metzgesfeld',
    '103': 'Metzgesfeld',
    '103a': 'Metzgesfeld',
    '104': 'Kallenhard',
    '105': 'Kallenhard',
    '106': 'Kallenhard',
    '107': 'Kallenhard',
    '108': 'Kallenhard exit',
    '108a': 'Kallenhard exit',
    '109': 'Kallenhard exit',
    '110': 'Kallenhard exit',
    '111': 'Kallenhard exit',
    '112': 'Wehrseifen',
    '112a': 'Wehrseifen',
    '113': 'Wehrseifen',
    '114': 'Wehrseifen',
    '115': 'Exmühle approach',
    '116': 'Exmühle approach',
    '117': 'Exmühle approach',
    '118': 'Exmühle',
    '119': 'Exmühle',
    '120': 'Exmühle',
    '121': 'Exmühle exit',
    '122': 'Exmühle exit',
    '123': 'Exmühle exit',
    '124': 'Exmühle exit',
    '125': 'Bergwerk',
    '125a': 'Bergwerk',
    '126': 'Bergwerk',
    '126a': 'Bergwerk',
    '127': 'Kesselchen 1',
    '128': 'Kesselchen 1',
    '129': 'Kesselchen 1',
    '130': 'Kesselchen 2',
    '131': 'Kesselchen 2',
    '132': 'Klostertal',
    '133': 'Klostertal',
    '134': 'Klostertal',
    '135': 'Klostertal',
    '136': 'Klostertal',
    '137': 'Klostertal',
    '138': 'Steilstrecke',
    '139': 'Steilstrecke',
    '140': 'Karussel entry',
    '141': 'Karussel entry',
    '142': 'Karussel',
    '143': 'Karussel',
    '144': 'Karussel',
    '145': 'Karussel exit',
    '146': 'Karussel exit',
    '147': 'Karussel exit',
    '148': 'Hohe Acht',
    '149': 'Hohe Acht',
    '149a': 'Hohe Acht',
    '150': 'Hohe Acht',
    '151': 'Hohe Acht',
    '152': 'Hohe Acht',
    '153': 'Hedwigshöhe',
    '154': 'Hedwigshöhe',
    '155': 'Hedwigshöhe',
    '156': 'Wippermann',
    '157': 'Wippermann',
    '158': 'Wippermann',
    '159': 'Wippermann',
    '160': 'Eschbach',
    '161': 'Eschbach',
    '162': 'Eschbach',
    '163': 'Brünnchen 1',
    '163a': 'Brünnchen 1',
    '164': 'Brünnchen 1',
    '165': 'Brünnchen 1',
    '166': 'Brünnchen 2',
    '167': 'Brünnchen 2',
    '168': 'Brünnchen 2',
    '169': 'Brünnchen 2',
    '170': 'Pflanzgarten',
    '171': 'Pflanzgarten',
    '172': 'Pflanzgarten',
    '173': 'Pflanzgarten',
    '174': 'Pflanzgarten',
    '175': 'Pflanzgarten',
    '176': 'Pflanzgarten',
    '177': 'Stefan Bellof S',
    '178': 'Stefan Bellof S',
    '178a': 'Schwalbenschwanz entry',
    '179': 'Schwalbenschwanz entry',
    '180': 'Schwalbenschwanz',
    '180a': 'Schwalbenschwanz',
    '181': 'Schwalbenschwanz',
    '182': 'Schwalbenschwanz',
    '183': 'Schwalbenschwanz',
    '184': 'Schwalbenschwanz',
    '185': 'Galgenkopf',
    '186': 'Galgenkopf',
    '187': 'Galgenkopf',
    '188': 'Döttinger Höhe 1',
    '189': 'Döttinger Höhe 1',
    '190': 'Döttinger Höhe 1',
    '191': 'Döttinger Höhe 1',
    '192': 'Döttinger Höhe 1',
    '193': 'Döttinger Höhe 2',
    '194': 'Döttinger Höhe 2',
    '195': 'Döttinger Höhe 3',
    '196': 'Döttinger Höhe 3',
    '197': 'Döttinger Höhe 3',
    '198': 'Döttinger Höhe 3',
    '199': 'Döttinger Höhe 3',
    '200': 'Tiergarten',
    '200a': 'Tiergarten',
    '201': 'Tiergarten',
    '202': 'Hohenrain',
    '203': 'Hohenrain',
    '204': 'Hohenrain',
    '205': 'Hohenrain',
    '206': 'GP transition',
    '207': 'GP transition'
}


def _parse_objects(data):
    result = {}
    tokens = data.decode()[11:].split(';')

    for token in tokens:
        split = TOKEN_SPLIT_REGEX.match(token)
        if split:
            field, idx, value = split.group('field'), split.group('idx'), split.group('value')

            if idx:
                result.setdefault(idx, {})[field] = value

    return result


class Nurburgring(object):
    log = Logger()

    def __init__(self, app=OVER_IP_APP, verbose=False, ignore_zones=[]):
        self._zones = {}
        self._verbose = verbose
        self.app = app
        self.ignore_zones = ignore_zones
        getPage(bytes(MARSHAL_POST_ADDRESS_URL.format(self.app), 'utf-8')).addCallbacks(self._parse_addresses, self._handle_errback)

    def _parse_addresses(self, data):
        addresses = _parse_objects(data)
        self._names = {}
        for obj in list(addresses.values()):
            if "geoobjectid" in obj:
                self._names[obj['geoobjectid']] = base64.b64decode(obj.get('name')).lower()
        getPage(bytes(MARSHAL_POST_ID_URL.format(self.app), 'utf-8')).addCallbacks(self._parse_marshal_posts, self._handle_errback)

    def _parse_marshal_posts(self, data):
        objs = _parse_objects(data)
        self._marshal_posts = {}

        for obj in list(objs.values()):
            self._marshal_posts[obj['ruleid']] = self._names.get(obj['refid'], obj['refid'])

            if self._verbose:
                print(self._marshal_posts)

        self.log.info('Starting poll for GPSauge NBR data...')
        LoopingCall(self._update_zones).start(10)

    def _update_zones(self):
        getPage(bytes(ACTIVE_ZONES_URL.format(self.app), 'utf-8')).addCallbacks(self._parse_zones, self._handle_errback)

    def _parse_zones(self, data):
        parsed_data = simplejson.loads(data)
        self._zones = {}

        zones = parsed_data.get('data', [])

        for zt, zone in zones:
            post_num = self._marshal_posts.get(str(zone), b'')
            if hasattr(post_num, 'decode'):
                post_num = post_num.decode('utf-8')
            if post_num not in self.ignore_zones:
                self._zones[zone] = (zt, post_num, MARSHAL_POST_LOCATIONS.get(post_num, ''))

        if self._verbose:
            print(self._zones)

    def _handle_errback(self, err):
        self.log.error("Encountered an error: {err}", err=err)

    def active_zones(self):
        return copy.copy(self._zones)


if __name__ == '__main__':
    n = Nurburgring(verbose=True)
    reactor.run()
