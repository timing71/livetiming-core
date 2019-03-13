from collections import defaultdict
from livetiming.service import Service as lt_service
from livetiming.racing import Stat, FlagStatus
from twisted.internet import reactor
from twisted.internet.protocol import Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import LoopingCall

import argparse
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


def create_protocol(service):
    class HHProtocol(Protocol):
        def log(self, *args, **kwargs):
            if service:
                service.log.info(*args, **kwargs)
            else:
                print args, kwargs

        def connect(self, endpoint):
            self.log("Connecting to HH Timing at {endpoint}...", endpoint=endpoint)
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
            if service:
                service.notify_update()

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

        @handler('HHTiming.Core.Definitions.Communication.Messages.CarGpsPointMessage')
        def ignore(self, _):
            pass

    return HHProtocol()


CAR_STATE_MAP = {
    0: 'PIT'
}


FLAG_STATE_MAP = {
    0: FlagStatus.NONE
}


def _extract_sector(sectorIndex, car):
    current_sectors = car.get('current_sectors', {})
    previous_sectors = car.get('previous_sectors', {})

    sector = str(sectorIndex)

    if sector in current_sectors:
        return (current_sectors[sector]['SectorTime'], '')
    elif sector in previous_sectors:
        return (previous_sectors[sector]['SectorTime'], 'old')
    else:
        return ('', '')


def parse_extra_args(extra_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="HH host", default='live-api.hhtiming.com')
    parser.add_argument("--port", help="HH port", type=int, default=24688)

    a, _ = parser.parse_known_args(extra_args)
    return a


class Service(lt_service):
    auto_poll = False

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)
        self.protocol = create_protocol(self)
        self._extra_args = parse_extra_args(extra_args)

        self._due_publish_state = False

    def notify_update(self):
        self._due_publish_state = True

    def start(self):
        def maybePublish():
            if self._due_publish_state:
                self._updateAndPublishRaceState()
                self._due_publish_state = False
        LoopingCall(maybePublish).start(1)

        self.protocol.connect(
            TCP4ClientEndpoint(
                reactor,
                self._extra_args.host,
                self._extra_args.port
            )
        )

        super(Service, self).start()

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.STATE,
            Stat.CLASS,
            Stat.DRIVER,
            Stat.TEAM,
            Stat.CAR,
            Stat.LAPS,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP,
            Stat.PITS
        ]

    def getName(self):
        return self.protocol.session.get('EventName', 'Live Timing')

    def getDefaultDescription(self):
        return self.protocol.session.get('SessionDescription')

    def getRaceState(self):
        return {
            'cars': self._map_cars(),
            'session': self._map_session()
        }

    def _map_cars(self):
        cars = []
        for num, car in self.protocol.cars.iteritems():
            print car
            driver = car.get('driver', {})

            car_data = [
                num,
                CAR_STATE_MAP.get(car.get('Status'), car.get('Status')),
                car.get('CategoryID'),
                u"{} {}".format(driver.get('FirstName', ''), driver.get('LastName', '')).strip(),
                car.get('TeamName'),
                car.get('CarMake'),
                car.get('NumberOfLaps')
            ]

            for s in range(3):
                car_data.append(
                    _extract_sector(
                        s + 1,
                        car
                    )
                )

            car_data += [
                (car.get('LapTime', ''), ''),
                (car.get('BestLaptime', ''), '')
            ]

            cars.append(car_data)
        return cars

    def _map_session(self):
        # print self.protocol.session.keys()
        return {
            'flagState': FLAG_STATE_MAP.get(self.protocol.session.get('TrackStatus', 0), FlagStatus.NONE).name.lower()
        }


if __name__ == '__main__':
    hh = create_protocol(None)
    hh.connect(TCP4ClientEndpoint(reactor, 'live-api.hhtiming.com', 24688))
    reactor.run()
