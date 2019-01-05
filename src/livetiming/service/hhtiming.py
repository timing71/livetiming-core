from collections import defaultdict
from livetiming.service import Service as lt_service
from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol

import inspect
import simplejson

END_OF_MESSAGE = '<EOM>'


def handler(msg_type):
    def inner(func):
        func.handles_message = msg_type
        return func
    return inner


def update_present_values(source, destination):
    for key, val in source.iteritems():
        if val != -1:
            destination[key] = val


class HHProtocol(Protocol):

    def connect(self, endpoint):
        print "Connecting to HH Timing..."
        return connectProtocol(endpoint, self)

    def connectionMade(self):
        self.cars = defaultdict(dict)
        self.track = {}
        self.session = {}
        self._buffer = ''

        self._handlers = {}

        for name, func in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(func, 'handles_message'):
                self._handlers[func.handles_message] = func

    def dataReceived(self, data):
        self._buffer += data
        while END_OF_MESSAGE in self._buffer:
            msg, _, rest = self._buffer.partition(END_OF_MESSAGE)
            self.handleMessage(msg)
            self._buffer = rest

    def handleMessage(self, msg):
        parsed_msg = simplejson.loads(msg)
        msg_type = parsed_msg.pop('$type').split(',')[0]

        if msg_type in self._handlers:
            self._handlers[msg_type](parsed_msg)
        else:
            print 'Unhandled message type {}'.format(msg_type)
            print parsed_msg
            print '----'

        print map(lambda kv: (kv[0], kv[1]['TimelineCrossingTimeOfDay']), self.cars['10'].get('current_sectors', {}).iteritems())

    @handler('HTiming.Core.Definitions.Communication.Messages.HeartbeatMessage')
    def heartbeat(self, data):
        update_present_values(data, self.session)

    @handler('HTiming.Core.Definitions.Communication.Messages.CompetitorMessage')
    def competitor(self, data):
        car = self.cars[data['CompetitorID']]
        update_present_values(data, car)

    @handler('HTiming.Core.Definitions.Communication.Messages.DriverMessage')
    def driver(self, data):
        if data.pop('IsInCar'):
            car = self.cars[data.pop('CarID')]
            car['driver'] = data

    @handler('HTiming.Core.Definitions.Communication.Messages.AdvSectorTimeLineCrossing')
    def adv_sector_crossing(self, data):
        car = self.cars[data.pop('CompetitorNumber')]
        current_sectors = car.setdefault('current_sectors', {})
        current_sectors[data.pop('TimelineNumber')] = data

    @handler('HTiming.Core.Definitions.Communication.Messages.EventMessage')
    def event(self, data):
        update_present_values(data, self.session)

    @handler('HTiming.Core.Definitions.Communication.Messages.SessionInfoMessage')
    def session_info(self, data):
        update_present_values(data, self.session)

    @handler('HTiming.Core.Definitions.Communication.Messages.AdvTrackInformationMessage')
    def adv_track_info(self, data):
        update_present_values(data, self.track)
        print data

    @handler('HTiming.Core.Definitions.Communication.Messages.LaptimeResultsUpdateMessage')
    def laptime_results_update(self, data):
        car = self.cars[data.pop('CarID')]
        update_present_values(data, car)

    @handler('HTiming.Core.Definitions.Communication.Messages.BasicTimeCrossingMessage')
    def basic_time_crossing(self, data):
        car = self.cars[data.pop('CarID')]
        update_present_values(data, car)
        car['previous_sectors'] = car.get('current_sectors', {})
        car['current_sectors'] = {}

    @handler('HTiming.Core.Definitions.Communication.Messages.PitInMessage')
    def pit_in(self, data):
        car = self.cars[data.pop('CarID')]
        car['InPit'] = True

    @handler('HTiming.Core.Definitions.Communication.Messages.PitOutMessage')
    def pit_out(self, data):
        car = self.cars[data.pop('CarID')]
        car['InPit'] = False


class Service(lt_service):
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.protocol = create_protocol(self)


if __name__ == '__main__':
    hh = HHProtocol()
    hh.connect(TCP4ClientEndpoint(reactor, 'live-api.hhtiming.com', 24689))
    reactor.run()
