from livetiming.racing import Stat


def _get_field(colspec, car, field):
    if field in colspec:
        return car[colspec.index(field)]
    return None


def _set_field(colspec, car, field, value):
    if field in colspec:
        car[colspec.index(field)] = value


def LaptimeEvent(colspec, race_num, lap_time, flags):
    def process(state):
        car = state[race_num]
        prev_lap_count = _get_field(colspec, car, Stat.LAPS)
        prev_best = _get_field(colspec, car, Stat.BEST_LAP)

        _set_field(colspec, car, Stat.LAST_LAP, (lap_time, flags))
        _set_field(colspec, car, Stat.LAPS, prev_lap_count + 1)
        if not prev_best or lap_time < prev_best[0]:
            _set_field(colspec, car, Stat.BEST_LAP, (lap_time, 'pb'))
    return process


_sector_by_num = {
    1: (Stat.S1, Stat.BS1),
    2: (Stat.S2, Stat.BS2),
    3: (Stat.S3, Stat.BS3),
}


def SectorEvent(colspec, race_num, sector_num, sector_time, flag):
    s_idx, bs_idx = _sector_by_num[sector_num]

    def process(state):
        car = state[race_num]
        prev_best = _get_field(colspec, car, bs_idx)

        _set_field(colspec, car, s_idx, (sector_time, flag))
        if not prev_best or sector_time < prev_best[0]:
            _set_field(colspec, car, bs_idx, (sector_time, 'pb'))
    return process
