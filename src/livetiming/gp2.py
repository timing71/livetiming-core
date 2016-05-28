import urllib2
import simplejson
from autobahn.twisted.websocket import connectWS, WebSocketClientFactory, WebSocketClientProtocol
from twisted.internet import reactor

def getToken():
    tokenData = simplejson.load(urllib2.urlopen("http://gpserieslivetiming.cloudapp.net/streaming/negotiate?clientProtocol=1.5"))
    return (tokenData["ConnectionId"], tokenData["ConnectionToken"])

def getWebSocketURL(token):
    return "ws://gpserieslivetiming.cloudapp.net/streaming/connect?transport=webSockets&clientProtocol=1.5&connectionToken={}&connectionData=%5B%7B%22name%22%3A%22streaming%22%7D%5D&tid=9".format(urllib2.quote(token[1]))


class GP2ClientProtocol(WebSocketClientProtocol):
    
    def onConnect(self, response):
        print u"Connected: {}".format(response)

    def onOpen(self):
        self.sendMessage('{H: "streaming", M: "JoinFeeds", A: ["GP2", ["data", "weather", "status", "time"]], I: 0}')
        self.sendMessage('{"H":"streaming","M":"GetData2","A":["GP2",["data","statsfeed","weatherfeed","sessionfeed","trackfeed","timefeed"]],"I":1}')
        
    def onMessage(self, payload, isBinary):
        print(u"Text message received: {0}".format(payload.decode('utf8')))
        
        
if __name__ == "__main__":
    
    socketURL = getWebSocketURL(getToken())
    factory = WebSocketClientFactory(socketURL)
    factory.protocol = GP2ClientProtocol
    
    
    print "Connecting to {}".format(socketURL)

    connectWS(factory)
    reactor.run()