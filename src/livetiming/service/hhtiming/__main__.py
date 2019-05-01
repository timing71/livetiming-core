from .protocol import create_protocol
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint


hh = create_protocol(None)
hh.connect(TCP4ClientEndpoint(reactor, 'live-api.hhtiming.com', 24688))
reactor.run()
