from livetiming.racing import FlagStatus

_prev_leader_lap = 0


def receive_state_update(dc, old_state, new_state, colspec, timestamp, new_messages):
    global _prev_leader_lap

    changed = False
    flag = FlagStatus.fromString(new_state["session"].get("flagState", "none"))
    old_flag = FlagStatus.fromString(old_state["session"].get("flagState", "none"))
    if flag != old_flag or not dc.session.this_period:
        dc.flag_change(flag, timestamp)
        changed = True
    if dc.leader_lap != _prev_leader_lap:
        _prev_leader_lap = dc.leader_lap
        changed = True
    if changed:
        return [('session', get_data(dc))]
    else:
        return []


def get_data(dc):
    results = {
        'currentTimestamp': dc.latest_timestamp,
        'flagStats': dc.session.flag_periods,
        'leaderLap': dc.leader_lap
    }

    return results
