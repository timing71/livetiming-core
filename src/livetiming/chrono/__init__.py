from datetime import date, datetime
from livetiming.racing import Stat

import copy


class Event(object):
    def __init__(self, timestamp):
        self.timestamp = timestamp

    def __call__(self, state):
        '''
        Extension point: subclasses should implement this method to return
        a new state object with the relevant changes applied.
        '''
        pass

    def __str__(self):
        return f"{self.timestamp} ({datetime.fromtimestamp(self.timestamp).strftime('%H:%M:%S.%f')}): {self.__class__.__name__}"


class FlagEvent(Event):
    def __init__(self, timestamp, flagState):
        super().__init__(timestamp)
        self.flagState = flagState

    def __call__(self, state):
        new_state = copy.deepcopy(state)
        new_state['session']['flagState'] = self.flagState
        return new_state

    def __str__(self):
        return f"{super().__str__()} => {self.flagState}"


class CarEvent(Event):
    def __init__(self, timestamp, colspec, race_num):
        super().__init__(timestamp)
        self._colspec = colspec
        self._race_num = race_num

    def _get_car(self, state):
        return copy.copy(state['cars'][self._race_num])

    def _get_field(self, car, field):
        if field in self._colspec:
            return car[self._colspec.index(field)]
        return None

    def _set_field(self, car, field, value):
        if field in self._colspec:
            car[self._colspec.index(field)] = value

    def _updated_state(self, state, car):
        new_state = copy.deepcopy(state)
        new_state['cars'].update({self._race_num: car})
        return new_state

    def __str__(self):
        return f"{super().__str__()} => {self._race_num}"


class LaptimeEvent(CarEvent):
    def __init__(self, timestamp, colspec, race_num, lap_time, flags):
        super(LaptimeEvent, self).__init__(timestamp, colspec, race_num)
        self._lap_time = lap_time
        self._flags = flags

    def __call__(self, state):
        car = self._get_car(state)
        prev_lap_count = self._get_field(car, Stat.LAPS)
        prev_best = self._get_field(car, Stat.BEST_LAP)

        self._set_field(car, Stat.LAST_LAP, (self._lap_time, self._flags))
        self._set_field(car, Stat.LAPS, prev_lap_count + 1)
        if self._get_field(car, Stat.STATE) in ['N/S', 'OUT']:
            self._set_field(car, Stat.STATE, 'RUN')

        if not prev_best or isinstance(prev_best[0], str) or self._lap_time < prev_best[0]:
            self._set_field(car, Stat.BEST_LAP, (self._lap_time, 'old'))
            self._set_field(car, Stat.LAST_LAP, (self._lap_time, 'pb'))

        car[-1][0] = self.timestamp
        car[-1][4] = 0

        return self._updated_state(state, car)

    def __str__(self):
        return f"{super().__str__()}: {self._lap_time}"


_sector_by_num = {
    1: (Stat.S1, Stat.BS1),
    2: (Stat.S2, Stat.BS2),
    3: (Stat.S3, Stat.BS3),
}


class SectorEvent(CarEvent):
    def __init__(self, timestamp, colspec, race_num, sector_num, sector_time, flag):
        super(SectorEvent, self).__init__(timestamp, colspec, race_num)
        self._sector_num = sector_num
        self._sector_time = sector_time
        self._flag = flag

    def __call__(self, state):
        s_idx, bs_idx = _sector_by_num[self._sector_num]

        car = self._get_car(state)
        prev_best = self._get_field(car, bs_idx)

        self._set_field(car, s_idx, (self._sector_time, self._flag))
        if not prev_best or not prev_best[0] or self._sector_time < prev_best[0]:
            self._set_field(car, s_idx, (self._sector_time, 'pb'))
            self._set_field(car, bs_idx, (self._sector_time, 'old'))

        for sn, stats in _sector_by_num.items():
            if sn != self._sector_num:
                sec = self._get_field(car, stats[0])
                if sec[1] == '':
                    self._set_field(
                        car,
                        stats[0],
                        [
                            sec[0],
                            'old'
                        ]
                    )

        car[-1][self._sector_num] = self.timestamp
        car[-1][4] = self._sector_num

        if self._get_field(car, Stat.STATE) == 'N/S':
            self._set_field(car, Stat.STATE, 'RUN')

        return self._updated_state(state, car)


class PitInEvent(CarEvent):
    def __init__(self, timestamp, colspec, race_num, increment_laps=True):
        super().__init__(timestamp, colspec, race_num)
        self._increment_laps = increment_laps

    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.STATE, "PIT")
        current_pits = self._get_field(car, Stat.PITS) or 0
        current_laps = self._get_field(car, Stat.LAPS) or 0
        self._set_field(car, Stat.PITS, current_pits + 1)
        if self._increment_laps:
            self._set_field(car, Stat.LAPS, current_laps + 1)

        return self._updated_state(state, car)


class PitOutEvent(CarEvent):
    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.STATE, "OUT")

        return self._updated_state(state, car)


class DriverChangeEvent(CarEvent):
    def __init__(self, timestamp, colspec, race_num, driver):
        super(DriverChangeEvent, self).__init__(timestamp, colspec, race_num)
        self.driver = driver

    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.DRIVER, self.driver)
        return self._updated_state(state, car)
