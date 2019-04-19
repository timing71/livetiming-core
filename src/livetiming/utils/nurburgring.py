# -*- coding: utf-8 -*-
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from twisted.web import client
from twisted.web.http_headers import Headers

import base64
import copy
import re
import simplejson

OVER_IP_APP = 'IPHNGR24'
MARSHAL_POST_ADDRESS_URL = 'https://www.apioverip.de/?action=list&module=geoobject&nozlib=1&overipapp={}&type=address'.format(OVER_IP_APP)
MARSHAL_POST_ID_URL = 'https://www.apioverip.de/?action=list&module=rule&nozlib=1&overipapp={}'.format(OVER_IP_APP)
ACTIVE_ZONES_URL = 'https://dev.apioverip.de/racing/rules/active?overipapp={}'.format(OVER_IP_APP)
# TRACK_STATE_URL = 'https://www.apioverip.de/?action=getconfig&mode=single&module=racing&nozlib=1&overipapp={}&param=track_state'.format(OVER_IP_APP)

TOKEN_SPLIT_REGEX = re.compile('^(?P<field>[a-z]+([0-9]+_)?)((?P<idx>[0-9]+)):=(?P<value>.*)?$')

MARSHAL_POST_LOCATIONS = {
    '1': 'Start/Finish',
    '2': 'Start/Finish',
    '2a': 'Start/Finish',
    '3': 'Start/Finish',
    '4': 'Haug-Haken',
    '4a': 'Haug-Haken',
    '5': 'Haug-Haken',
    '6': 'Mercedes arena',
    '7': 'Mercedes arena',
    '8': 'Mercedes arena',
    '9': 'Mercedes arena',
    '10': 'Yokohama-S',
    '11': 'Yokohama-S',
    '12': 'Yokohama - Valvoline',
    '13': 'Yokohama - Valvoline',
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
    '27': 'Schumacher',
    '28': 'Schumacher',
    '29': 'Schumacher',
    '30': 'Schumacher',
    '31': 'Ravenol',
    '32': 'Ravenol',
    '33a': 'Ravenol',
    '33': 'Ravenol',
    '34': 'Ravenol',
    '35': 'Bilstein',
    '36': 'Bilstein',
    '37': 'Bilstein',
    '38': 'Bilstein – Advan',
    '39': 'Bilstein – Advan',
    '40': 'Advan-Bogen',
    '40a': 'Advan-Bogen',
    '41': 'Bogen-Veedol',
    '42': 'Bogen-Veedol',
    '42a': 'Bogen-Veedol',
    '42b': 'Bogen-Veedol',
    '43': 'Bogen-Veedol',
    '44': 'Jaguar',
    '45': 'Jaguar',
    '46': 'Jaguar',
    '47': 'Jaguar',
    '48': 'Jaguar',
    '49': 'Jaguar',
    '50': 'Start/Finish',
    '60': 'Nordschliefe transition',
    '61': 'Nordschliefe transition',
    '62': 'Nordschliefe transition',
    '63': 'Hatzenbach approach',
    '64': 'Hatzenbach approach',
    '65': 'Hatzenbach approach',
    '66': 'Hatzenbach approach',
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
    '82': 'Schwedenkreuz',
    '83': 'Schwedenkreuz',
    '84': 'Schwedenkreuz',
    '85': 'Schwedenkreuz',
    '86': 'Schwedenkreuz',
    '87': 'Schwedenkreuz',
    '88': 'Aremberg',
    '89': 'Aremberg',
    '90': 'Aremberg',
    '91': 'Aremberg',
    '92': 'Aremberg',
    '92a': 'Aremberg',
    '93': 'Aremberg',
    '94': 'Aremberg',
    '95': 'Fuchsröhre',
    '96': 'Fuchsröhre',
    '97': 'Fuchsröhre',
    '98': 'Fuchsröhre',
    '98a': 'Fuchsröhre',
    '99': 'Adenauer Forst',
    '100': 'Adenauer Forst',
    '100a': 'Adenauer Forst',
    '101': 'Metzgesfeld',
    '102': 'Metzgesfeld',
    '103': 'Metzgesfeld',
    '103a': 'Metzgesfeld',
    '104': 'Kallenhard',
    '105': 'Kallenhard',
    '106': 'Kallenhard',
    '107': 'Kallenhard',
    '108': 'Kallenhard',
    '108a': 'Kallenhard',
    '109': 'Kallenhard',
    '110': 'Wehrseifen',
    '111': 'Wehrseifen',
    '112': 'Exmühle',
    '112a': 'Exmühle',
    '113': 'Exmühle',
    '114': 'Exmühle',
    '115': 'Exmühle',
    '116': 'Exmühle',
    '117': 'Exmühle',
    '118': 'Exmühle',
    '119': 'Exmühle',
    '120': 'Exmühle',
    '121': 'Exmühle',
    '122': 'Exmühle - Bergwerk',
    '123': 'Exmühle - Bergwerk',
    '124': 'Exmühle - Bergwerk',
    '125': 'Bergwerk',
    '125a': 'Bergwerk',
    '126': 'Bergwerk',
    '126a': 'Bergwerk',
    '127': 'Kesselchen',
    '128': 'Kesselchen',
    '129': 'Kesselchen',
    '130': 'Kesselchen',
    '131': 'Kesselchen',
    '132': 'Klostertal',
    '133': 'Klostertal',
    '134': 'Klostertal',
    '135': 'Klostertal',
    '136': 'Klostertal',
    '137': 'Klostertal',
    '138': 'Caracciola – Karussel',
    '139': 'Caracciola – Karussel',
    '140': 'Caracciola – Karussel',
    '141': 'Caracciola – Karussel',
    '142': 'Caracciola – Karussel',
    '143': 'Caracciola – Karussel',
    '144': 'Caracciola – Karussel',
    '145': 'Caracciola – Karussel',
    '146': 'Karussel exit',
    '147': 'Karussel exit',
    '148': 'Hohe Acht',
    '149': 'Hohe Acht',
    '149a': 'Hohe Acht',
    '150': 'Hohe Acht',
    '151': 'Hohe Acht',
    '152': 'Hohe Acht',
    '153': 'Hohe Acht',
    '154': 'Hohe Acht',
    '155': 'Wippermann',
    '156': 'Wippermann',
    '157': 'Wippermann',
    '158': 'Eschbach',
    '159': 'Eschbach',
    '160': 'Eschbach',
    '161': 'Eschbach',
    '162': 'Eschbach',
    '163': 'Brünnchen',
    '163a': 'Brünnchen',
    '164': 'Brünnchen',
    '165': 'Brünnchen',
    '166': 'Brünnchen',
    '167': 'Brünnchen',
    '168': 'Brünnchen',
    '169': 'Pflanzgarten',
    '170': 'Pflanzgarten',
    '171': 'Pflanzgarten',
    '172': 'Pflanzgarten',
    '173': 'Pflanzgarten',
    '174': 'Pflanzgarten',
    '175': 'Pflanzgarten',
    '176': 'Pflanzgarten',
    '177': 'Pflanzgarten',
    '178': 'Pflanzgarten',
    '178a': 'Schwalbenschwanz',
    '179': 'Schwalbenschwanz',
    '180a': 'Schwalbenschwanz',
    '180': 'Schwalbenschwanz',
    '181': 'Schwalbenschwanz',
    '182': 'Schwalbenschwanz',
    '183': 'Schwalbenschwanz',
    '184': 'Schwalbenschwanz',
    '185': 'Galgenkopf',
    '186': 'Galgenkopf',
    '187': 'Galgenkopf',
    '188': 'Döttinger Höhe',
    '189': 'Döttinger Höhe',
    '190': 'Döttinger Höhe',
    '191': 'Döttinger Höhe',
    '192': 'Döttinger Höhe',
    '193': 'Döttinger Höhe',
    '194': 'Döttinger Höhe',
    '195': 'Döttinger Höhe',
    '196': 'Touristen Einfahrt',
    '197': 'Touristen Einfahrt',
    '198': 'Touristen Einfahrt',
    '199': 'Touristen Einfahrt',
    '200': 'Tiergarten',
    '200a': 'Tiergarten',
    '201': 'Tiergarten',
    '202': 'Tiergarten',
    '203': 'Hohenrain',
    '204': 'Hohenrain',
    '205': 'Hohenrain',
    '206': 'Hohenrain',
    '207': 'Hohenrain'
}


def _parse_objects(data):
    result = {}
    tokens = data[11:].split(';')

    for token in tokens:
        split = TOKEN_SPLIT_REGEX.match(token)
        if split:
            field, idx, value = split.group('field'), split.group('idx'), split.group('value')

            if idx:
                result.setdefault(idx, {})[field] = value

    return result


class Nurburgring(object):
    log = Logger()

    def __init__(self, verbose=False):
        self._zones = {}
        self._verbose = verbose
        client.getPage(MARSHAL_POST_ADDRESS_URL).addCallbacks(self._parse_addresses, self._handle_errback)

    def _parse_addresses(self, data):
        addresses = _parse_objects(data)
        self._names = {}
        for obj in addresses.values():
            if "geoobjectid" in obj:
                self._names[obj['geoobjectid']] = base64.b64decode(obj.get('name')).lower()
        client.getPage(MARSHAL_POST_ID_URL).addCallbacks(self._parse_marshal_posts, self._handle_errback)

    def _parse_marshal_posts(self, data):
        objs = _parse_objects(data)
        self._marshal_posts = {}

        for obj in objs.values():
            self._marshal_posts[obj['ruleid']] = self._names.get(obj['refid'], obj['refid'])

            if self._verbose:
                print self._marshal_posts

        LoopingCall(self._update_zones).start(10)

    def _update_zones(self):
        client.getPage(ACTIVE_ZONES_URL).addCallbacks(self._parse_zones, self._handle_errback)

    def _parse_zones(self, data):
        parsed_data = simplejson.loads(data)
        self._zones = {}

        zones = parsed_data.get('data', [])

        for zt, zone in zones:
            post_num = self._marshal_posts.get(str(zone), '')
            self._zones[zone] = (zt, post_num, MARSHAL_POST_LOCATIONS.get(post_num, ''))

        if self._verbose:
            print self._zones

    def _handle_errback(self, err):
        self.log.error("Encountered an error: {err}", err=err)

    def active_zones(self):
        return copy.copy(self._zones)


if __name__ == '__main__':
    n = Nurburgring(True)
    reactor.run()