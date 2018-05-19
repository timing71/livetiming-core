from autobahn.twisted.websocket import connectWS, WebSocketClientProtocol
from livetiming.service import Service as lt_service, ReconnectingWebSocketClientFactory
from livetiming.utils.meteor import MeteorClient, DDPProtoclFactory


class AlkamelV2Client(MeteorClient):
    def __init__(self):
        MeteorClient.__init__(self)
        self._factory = ReconnectingWebSocketClientFactory('wss://livetiming.alkamelsystems.com/sockjs/261/t48ms2xd/websocket')
        self._factory.protocol = DDPProtoclFactory(self)
        connectWS(self._factory)

    def onConnect(self):
        self.subscribe('livetimingFeed', ['fiaformulae'], self.recv_feeds)
        self.subscribe('sessionClasses', [None])
        self.subscribe('trackInfo', [None])

    def recv_feeds(self, _):
        print "Got feeds:", self.find('feeds')


class Service(lt_service):
    def __init__(self, args, extra_args):
        lt_service.__init__(self, args, extra_args)

        self._client = AlkamelV2Client()

    def getName(self):
        return "Al Kamel v2"

    def getDefaultDescription(self):
        return 'Testing'

    def getColumnSpec(self):
        return []

    def getRaceState(self):
        print self._client.collection_data
        return {
            'session': {
                'flagState': 'none'
            },
            'cars': []
        }
