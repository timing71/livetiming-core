from livetiming.racing import Stat

import copy


class Event(object):
    def __init__(self, timestamp, colspec, race_num):
        self.timestamp = timestamp
        self._colspec = colspec
        self._race_num = race_num

    def __call__(self, state):
        pass

    def _get_car(self, state):
        return copy.copy(state[self._race_num])

    def _get_field(self, car, field):
        if field in self._colspec:
            return car[self._colspec.index(field)]
        return None

    def _set_field(self, car, field, value):
        if field in self._colspec:
            car[self._colspec.index(field)] = value

    def _updated_state(self, state, car):
        new_state = copy.deepcopy(state)
        new_state.update({self._race_num: car})
        return new_state


class LaptimeEvent(Event):
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

        if not prev_best or self._lap_time < prev_best[0]:
            self._set_field(car, Stat.BEST_LAP, (self._lap_time, 'pb'))
            self._set_field(car, Stat.LAST_LAP, (self._lap_time, 'pb'))

        car[-1][0] = self.timestamp
        car[-1][4] = 0

        return self._updated_state(state, car)


_sector_by_num = {
    1: (Stat.S1, Stat.BS1),
    2: (Stat.S2, Stat.BS2),
    3: (Stat.S3, Stat.BS3),
}


class SectorEvent(Event):
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
        if not prev_best or self._sector_time < prev_best[0]:
            self._set_field(car, bs_idx, (self._sector_time, 'pb'))

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


class PitInEvent(Event):
    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.STATE, "PIT")
        current_pits = self._get_field(car, Stat.PITS) or 0
        current_laps = self._get_field(car, Stat.LAPS) or 0
        self._set_field(car, Stat.PITS, current_pits + 1)
        self._set_field(car, Stat.LAPS, current_laps + 1)

        return self._updated_state(state, car)


class PitOutEvent(Event):
    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.STATE, "OUT")

        return self._updated_state(state, car)


class DriverChangeEvent(Event):
    def __init__(self, timestamp, colspec, race_num, driver):
        super(DriverChangeEvent, self).__init__(timestamp, colspec, race_num)
        self.driver = driver

    def __call__(self, state):
        car = self._get_car(state)
        self._set_field(car, Stat.DRIVER, self.driver)
        return self._updated_state(state, car)
