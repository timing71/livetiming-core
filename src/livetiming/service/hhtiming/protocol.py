from collections import defaultdict
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.protocol import Protocol

import inspect
import simplejson
import time


END_OF_MESSAGE = '<EOM>'


def handler(*msg_types):
    def inner(func):
        func.handles_message = msg_types
        return func
    return inner


def update_present_values(source, destination):
    for key, val in source.iteritems():
        if val != -1:
            destination[key] = val


def create_protocol(service, initial_state_file=None):
    class HHProtocol(Protocol):

        def __init__(self):
            self.cars = defaultdict(dict)
            self.track = {}
            self.session = {}
            self.messages = []

            self._handlers = {}

            for name, func in inspect.getmembers(self, predicate=inspect.ismethod):
                if hasattr(func, 'handles_message'):
                    for msg_type in func.handles_message:
                        self._handlers[msg_type] = func

        def log(self, *args, **kwargs):
            if service:
                service.log.info(*args, **kwargs)
            else:
                print args, kwargs

        def connect(self, endpoint):
            self.log("Connecting to HH Timing at {endpoint}...", endpoint=endpoint)
            return connectProtocol(endpoint, self)

        def connectionMade(self):
            self._buffer = ''

        def dump_data(self):
            return {
                'cars': self.cars,
                'track': self.track,
                'session': self.session,
                'messages': self.messages
            }

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
            if service:
                service.notify_update(msg_type)

        @handler('HTiming.Core.Definitions.Communication.Messages.HeartbeatMessage')
        def heartbeat(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

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
            sector_index = data.pop('TimelineNumber')
            current_sectors[sector_index] = data
            car['InPit'] = False

            pb_sectors = car.setdefault('PersonalBestSectors', {})
            if sector_index in pb_sectors:
                pb_sectors[sector_index] = min(data['SectorTime'], pb_sectors[sector_index])
            else:
                pb_sectors[sector_index] = data['SectorTime']

        @handler('HTiming.Core.Definitions.Communication.Messages.EventMessage')
        def event(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler('HTiming.Core.Definitions.Communication.Messages.SessionInfoMessage')
        def session_info(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()
            print "Session type: {}".format(data.get('SessionType', 'unset'))

        @handler('HTiming.Core.Definitions.Communication.Messages.AdvTrackInformationMessage')
        def adv_track_info(self, data):
            update_present_values(data, self.track)

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
            car['OutLap'] = False
            car['InPit'] = False

        @handler('HTiming.Core.Definitions.Communication.Messages.PitInMessage')
        def pit_in(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = True
            car['OutLap'] = False
            car['Pits'] = car.get('Pits', 0) + 1

        @handler('HTiming.Core.Definitions.Communication.Messages.PitOutMessage')
        def pit_out(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = False
            car['OutLap'] = True

        @handler('HTiming.Core.Definitions.Communication.Messages.GeneralRaceControlMessage')
        def race_control_message(self, data):
            self.messages.append((data['MessageReceivedTime'], data['MessageString']))

        @handler(
            'HHTiming.Core.Definitions.Communication.Messages.CarGpsPointMessage',
            'HTiming.Core.Definitions.Communication.Messages.InternalHHHeartbeatMessage',
            'HTiming.Core.Definitions.Communication.Messages.ClassInformationMessage'  # <- this one is pointless so long as ID == description
        )
        def ignore(self, _):
            pass

    protocol = HHProtocol()

    if initial_state_file:
        try:
            with open(initial_state_file, 'r') as statefile:
                state = simplejson.load(statefile)
                protocol.cars = state['cars']
                protocol.session = state['session']
                protocol.track = state['track']
                protocol.messages = state['messages']
        except IOError as e:
            protocol.log('Failed to load existing state file')
            print 'bad', e
            pass

    return protocol
