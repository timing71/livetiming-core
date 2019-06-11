from livetiming.messages import SlowZoneMessage
from livetiming.racing import FlagStatus


def state_with_flag(flag):
    return {
        'session': {
            'flagState': flag.name.lower()
        }
    }


def test_slow_zone_message():
    generator = SlowZoneMessage

    prev_state = state_with_flag(FlagStatus.GREEN)
    next_state = state_with_flag(FlagStatus.SLOW_ZONE)

    msgs = generator().process(prev_state, next_state)
    assert len(msgs) == 1
    assert msgs[0][1] == 'Track'
    assert msgs[0][2] == 'Slow zone(s) in operation'

    msgs = generator().process(next_state, prev_state)
    assert len(msgs) == 0
