from livetiming.racing import Stat
from livetiming.service import parse_args
from livetiming.service.hhtiming import create_protocol, Service

import os
import pytest


class ServiceForTest(Service):
    def _state_dump_file(self):
        return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data', 'hhtiming.json')


@pytest.fixture
def service():
    return ServiceForTest(*parse_args())


@pytest.fixture
def colspec(service):
    return service.getColumnSpec()


@pytest.fixture
def state(service):
    return service.getRaceState()


def test_calculate_order(colspec, state):

    race_num_idx = colspec.index(Stat.NUM)

    first_car = state['cars'][0]
    second_car = state['cars'][1]

    assert first_car[race_num_idx] == '47'
    assert second_car[race_num_idx] == '23'


def test_calculate_gap(service, colspec, state):

    gap_idx = colspec.index(Stat.GAP)
    int_idx = colspec.index(Stat.INT)

    first_car = state['cars'][0]
    second_car = state['cars'][1]

    assert first_car[gap_idx] == ''
    assert first_car[int_idx] == ''

    assert second_car[gap_idx] == second_car[int_idx]
    assert second_car[gap_idx] == pytest.approx(4.123, 0.001)
