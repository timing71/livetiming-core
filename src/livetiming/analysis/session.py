from livetiming.racing import FlagStatus


def receiveStateUpdate(dc, old_state, new_state, colspec, timestamp):
    flag = FlagStatus.fromString(new_state["session"].get("flagState", "none"))
    old_flag = FlagStatus.fromString(old_state["session"].get("flagState", "none"))
    if flag != old_flag or not dc.session.this_period:
        dc.flag_change(flag, timestamp)
        return True
    return False


def get_data(dc):
    results = {
        'currentTimestamp': dc.latest_timestamp,
        'flagStats': dc.session.flag_periods,
        'leaderLap': dc.leader_lap
    }

    return results
