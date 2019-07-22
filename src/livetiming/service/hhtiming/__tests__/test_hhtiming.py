from livetiming.racing import Stat
from livetiming.service import parse_args
from livetiming.service.hhtiming import create_protocol_factory, Service
from livetiming.service.hhtiming.service import calculate_race_gap

import os
import pytest
import simplejson


STATE_DUMP_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', 'hhtiming.json')


class ServiceForTest(Service):
    def _state_dump_file(self):
        return STATE_DUMP_FILE


@pytest.fixture
def service():
    s = ServiceForTest(*parse_args())
    p_factory = create_protocol_factory(s, STATE_DUMP_FILE)
    s.protocol = p_factory.buildProtocol('')
    return s


@pytest.fixture
def colspec(service):
    return service.getColumnSpec()


@pytest.fixture
def state(service):
    return service.getRaceState()


def test_exclude_course_cars(state):
    assert len(state['cars']) == 25


def test_calculate_order(colspec, state):

    race_num_idx = colspec.index(Stat.NUM)

    first_car = state['cars'][0]
    second_car = state['cars'][1]

    assert first_car[race_num_idx] == '47'
    assert second_car[race_num_idx] == '23'

    assert state['cars'][-1][race_num_idx] == '9'


def test_calculate_gap(service, colspec, state):

    gap_idx = colspec.index(Stat.GAP)
    int_idx = colspec.index(Stat.INT)

    first_car = state['cars'][0]
    second_car = state['cars'][1]

    assert first_car[gap_idx] == ''
    assert first_car[int_idx] == ''

    assert second_car[gap_idx] == second_car[int_idx]
    assert second_car[gap_idx] == pytest.approx(4.123, 0.001)

    last_car = state['cars'][-1]
    assert last_car[gap_idx] == '9 laps'
    assert last_car[int_idx] == '3 laps'

    car_off_lead_lap = state['cars'][-3]
    assert car_off_lead_lap[gap_idx] == '1 lap'


def test_compute_colspec(service, colspec):
    pre_sector_stats = [
        Stat.NUM,
        Stat.STATE,
        Stat.CLASS,
        Stat.TEAM,
        Stat.DRIVER,
        Stat.CAR,
        Stat.LAPS,
        Stat.GAP,
        Stat.INT
    ]

    assert colspec[:len(pre_sector_stats)] == pre_sector_stats

    post_sector_stats = [
        Stat.LAST_LAP,
        Stat.BEST_LAP,
        Stat.PITS
    ]

    assert colspec[-len(post_sector_stats):] == post_sector_stats

    non_sector_stats = len(pre_sector_stats) + len(post_sector_stats)

    expected_num_sectors = len(service.protocol.track['OrderedListOfOnTrackSectors']['$values'])
    assert len(colspec) == non_sector_stats + (expected_num_sectors * 2)


def test_race_gap():
    car_24 = {
        "LastElapsedTime": 1801.542,
        "NumberOfLaps": 18,
        "SessionTime": 1801.542,
        "current_sectors": {},
        "previous_sectors": {
            "1": {
                "SectorTime": 31.785,
                "SessionTime": 1734.07,
                "TimelineCrossingTimeOfDay": 1734.07
            },
            "2": {
                "SectorTime": 33.713,
                "SessionTime": 1767.783,
                "TimelineCrossingTimeOfDay": 1767.783
            },
            "3": {
                "SectorTime": 33.759,
                "SessionTime": 1801.542,
                "TimelineCrossingTimeOfDay": 1801.542
            }
        }
    }

    car_23 = {
        "LastElapsedTime": 1806.771,
        "NumberOfLaps": 18,
        "SessionTime": 1806.771,
        "current_sectors": {},
        "previous_sectors": {
            "1": {
                "SectorTime": 31.814,
                "SessionTime": 1739.213,
                "TimelineCrossingTimeOfDay": 1739.213
            },
            "2": {
                "SectorTime": 34.108,
                "SessionTime": 1773.321,
                "TimelineCrossingTimeOfDay": 1773.321
            },
            "3": {
                "SectorTime": 33.45,
                "SessionTime": 1806.771,
                "TimelineCrossingTimeOfDay": 1806.771
            }
        }
    }

    gap = calculate_race_gap(car_24, car_23)
    assert gap == pytest.approx(5.229, 0.001)

    car_22 = {
        "LastElapsedTime": 3784.674,
        "NumberOfLaps": 35,
        "SessionTime": 3784.674,
        "current_sectors": {
            "1": {
                "SectorTime": 32.007,
                "SessionTime": 3816.681,
                "TimelineCrossingTimeOfDay": 3816.681
            }
        },
        "previous_sectors": {
            "1": {
                "SectorTime": 106.196,
                "SessionTime": 3716.619,
                "TimelineCrossingTimeOfDay": 3716.619
            },
            "2": {
                "SectorTime": 34.451,
                "SessionTime": 3751.07,
                "TimelineCrossingTimeOfDay": 3751.07
            },
            "3": {
                "SectorTime": 33.604,
                "SessionTime": 3784.674,
                "TimelineCrossingTimeOfDay": 3784.674
            }
        }
    }
    car_25 = {
        "LastElapsedTime": 3804.58,
        "NumberOfLaps": 35,
        "current_sectors": {},
        "previous_sectors": {
            "1": {
                "SectorTime": 32.957,
                "SessionTime": 3733.793,
                "TimelineCrossingTimeOfDay": 3733.793
            },
            "2": {
                "SectorTime": 35.561,
                "SessionTime": 3769.354,
                "TimelineCrossingTimeOfDay": 3769.354
            },
            "3": {
                "SectorTime": 35.226,
                "SessionTime": 3804.58,
                "TimelineCrossingTimeOfDay": 3804.58
            }
        }
    }

    gap_2 = calculate_race_gap(car_22, car_25)
    assert gap_2 == pytest.approx(19.906, 0.001)

    leader = {
        "LastElapsedTime": 3902.73,
        "LastLaptime": 100.792,
        "NumberOfLaps": 38,
        "current_sectors": {},
        "previous_sectors": {
            "1": {
                "SectorTime": 27.501,
                "SessionTime": 3829.439,
                "TimelineCrossingTimeOfDay": 3829.439
            },
            "2": {
                "SectorTime": 39.09,
                "SessionTime": 3868.529,
                "TimelineCrossingTimeOfDay": 3868.529
            },
            "3": {
                "SectorTime": 34.201,
                "SessionTime": 3902.73,
                "TimelineCrossingTimeOfDay": 3902.73
            }
        }
    }

    nearly_lap_down = {
        "LastElapsedTime": 3881.792,
        "LastLaptime": 99.833,
        "NumberOfLaps": 37,
        "current_sectors": {},
        "previous_sectors": {
            "1": {
                "SectorTime": 27.853,
                "SessionTime": 3809.812,
                "TimelineCrossingTimeOfDay": 3809.812
            },
            "2": {
                "SectorTime": 37.886,
                "SessionTime": 3847.698,
                "TimelineCrossingTimeOfDay": 3847.698
            },
            "3": {
                "SectorTime": 34.094,
                "SessionTime": 3881.792,
                "TimelineCrossingTimeOfDay": 3881.792
            }
        }
    }

    gap_nearly_lap = calculate_race_gap(leader, nearly_lap_down)
    assert gap_nearly_lap == pytest.approx(79.854, 0.001)


@pytest.mark.skip(reason="Utility function that's occasionally useful")
def test_dump_state(service, state):

    outobj = {
        "manifest": service._createServiceRegistration()
    }

    outobj.update(state)

    with open('hhstate.json', 'w') as outfile:
        simplejson.dump(outobj, outfile)
