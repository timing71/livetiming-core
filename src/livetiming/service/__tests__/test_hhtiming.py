from livetiming.racing import Stat
from livetiming.service import parse_args
from livetiming.service.hhtiming import create_protocol, Service

import os
import pytest


STATE_DUMP_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', 'hhtiming.json')

class ServiceForTest(Service):
    def _state_dump_file(self):
        return STATE_DUMP_FILE


@pytest.fixture
def service():
    return ServiceForTest(*parse_args())


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
