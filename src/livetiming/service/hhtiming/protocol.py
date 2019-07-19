from collections import defaultdict
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from .types import MessageType

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
    for key, val in source.items():
        if val != -1:
            destination[key] = val


def create_protocol_factory(service, initial_state_file=None):
    class HHProtocol(Protocol):

        def __init__(self):
            self.cars = defaultdict(dict)
            self.track = {}
            self.session = {}
            self.weather = {}
            self.messages = []
            self.sector_states = {}

            self._handlers = {}

            for name, func in inspect.getmembers(self, predicate=inspect.ismethod):
                if hasattr(func, 'handles_message'):
                    for msg_type in func.handles_message:
                        self._handlers[msg_type] = func

            if service:
                if hasattr(service, 'set_protocol'):
                    service.set_protocol(self)

        def log(self, *args, **kwargs):
            if service:
                service.log.info(*args, **kwargs)
            else:
                print(args, kwargs)

        def connect(self, endpoint):
            self.log("Connecting to HH Timing at {endpoint}...", endpoint=endpoint)
            return connectProtocol(endpoint, self)

        def connectionMade(self):
            self.log('Established connection to HH Timing')
            self._buffer = ''

        def dump_data(self):
            return {
                'cars': self.cars,
                'track': self.track,
                'session': self.session,
                'sector_states': self.sector_states,
                'messages': self.messages
            }

        def dataReceived(self, data):
            self._buffer += data.decode('utf-8')
            while END_OF_MESSAGE in self._buffer:
                msg, _, rest = self._buffer.partition(END_OF_MESSAGE)
                self.handleMessage(msg)
                self._buffer = rest

        def handleMessage(self, msg):
            parsed_msg = simplejson.loads(msg)
            if parsed_msg and '$type' in parsed_msg:
                msg_type = parsed_msg.pop('$type').split(',')[0]

                if msg_type in self._handlers:
                    self._handlers[msg_type](parsed_msg.copy())
                else:
                    self.log(
                        'Unhandled message type {msg_type}: {data}',
                        msg_type=msg_type,
                        data=parsed_msg
                    )
                if service and hasattr(service, 'notify_update'):
                    service.notify_update(msg_type, parsed_msg)

        @handler(MessageType.HEARTBEAT)
        def heartbeat(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler(MessageType.COMPETITOR)
        def competitor(self, data):
            car = self.cars[data['CompetitorID']]
            update_present_values(data, car)

        @handler(MessageType.DRIVER)
        def driver(self, data):
            if data.pop('IsInCar'):
                car = self.cars[data.pop('CarID')]
                car['driver'] = data

        @handler(MessageType.DRIVER_UPDATE)
        def driver_update(self, data):
            car = self.cars[data.pop('CarID')]
            car['driver'] = data

        @handler(MessageType.SECTOR_TIME_ADV)
        def adv_sector_crossing(self, data):
            car_num = data.pop('CompetitorNumber')
            car = self.cars[car_num]
            current_sectors = car.setdefault('current_sectors', {})
            sector_index = data.pop('TimelineNumber')
            current_sectors[sector_index] = data
            if not data.get('IsStartFinish', False):
                car['InPit'] = False

            pb_sectors = car.setdefault('PersonalBestSectors', {})
            if sector_index in pb_sectors:
                pb_sectors[sector_index] = min(data['SectorTime'], pb_sectors[sector_index])
            else:
                pb_sectors[sector_index] = data['SectorTime']

        @handler(MessageType.SECTOR_TIME_UPDATE)
        def sector_time_update(self, data):
            car = self.cars[data.pop('CarID')]
            pb_sectors = car.setdefault('PersonalBestSectors', {})

            sector_idx = self._sector_from_name(data['SectorName'])
            if sector_idx:
                pb_sectors[sector_idx] = data['BestSectorTime']

        @handler(MessageType.EVENT)
        def event(self, data):
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler(MessageType.SESSION_INFO)
        def session_info(self, data):
            if self.session.get('SessionID') != data.get('SessionID'):
                self.cars.clear()
            update_present_values(data, self.session)
            self.session['LastUpdate'] = time.time()

        @handler(MessageType.TRACK_INFO_ADV)
        def adv_track_info(self, data):
            update_present_values(data, self.track)

        @handler(MessageType.LAPTIME_UPDATE)
        def laptime_results_update(self, data):
            car = self.cars[data.pop('CarID')]
            update_present_values(data, car)

        @handler(MessageType.BASIC_TIME_CROSSING)
        def basic_time_crossing(self, data):
            car = self.cars[data.pop('CarID')]
            update_present_values(data, car)
            car['previous_sectors'] = car.get('current_sectors', {})
            car['current_sectors'] = {}
            car['OutLap'] = False

        @handler(MessageType.PIT_IN)
        def pit_in(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = True
            car['OutLap'] = False
            car['Pits'] = car.get('Pits', 0) + 1

        @handler(MessageType.PIT_OUT)
        def pit_out(self, data):
            car = self.cars[data.pop('CarID')]
            car['InPit'] = False
            car['OutLap'] = True

        @handler(MessageType.RACE_CONTROL_MESSAGE)
        def race_control_message(self, data):
            self.messages.append((data['MessageReceivedTime'], data['MessageString']))

        @handler(
            MessageType.SPEED_TRAP,
            MessageType.TOP_SPEED_UPDATE
        )
        def speed_trap_message(self, data):
            car = self.cars[data.pop('CarID')]
            traps = car.setdefault('speed_traps', {})
            trap_name = data.pop('SpeedTrapName')
            trap_data = traps.setdefault(trap_name, {})
            update_present_values(data, trap_data)

        @handler(MessageType.SECTOR_STATUS)
        def sector_status(self, data):
            zone_name = data.pop('ZoneName')
            zone = self.sector_states.setdefault(zone_name, {})
            zone.update(data)

        @handler(MessageType.WEATHER)
        def weather_message(self, data):
            update_present_values(data, self.weather)

        @handler(
            MessageType.GPS,
            MessageType.INTERNAL_HEARTBEAT,
            MessageType.CLASS_INFORMATION  # <- this one is pointless so long as ID == description
        )
        def ignore(self, _):
            pass

        def _sector_from_name(self, sector_name):
            sectors = self.track.get('OrderedListOfOnTrackSectors', {}).get('$values', [])
            for s in sectors:
                if s['SectorName'] == sector_name:
                    return s['EndTimeLine']
            return None

    class HHProtocolFactory(ReconnectingClientFactory):
        def buildProtocol(self, addr):
            self.resetDelay()
            protocol = HHProtocol()

            if initial_state_file:
                try:
                    with open(initial_state_file, 'r') as statefile:
                        state = simplejson.load(statefile)
                        protocol.cars = state['cars']
                        protocol.session = state['session']
                        protocol.track = state['track']
                        protocol.messages = state['messages']
                        protocol.sector_states = state['sector_states']
                except Exception as e:
                    protocol.log('Failed to load existing state file')
                    print('bad', e)
                    pass

            return protocol

    return HHProtocolFactory()
