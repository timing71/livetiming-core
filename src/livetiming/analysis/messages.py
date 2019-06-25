def receive_state_update(dc, old_state, new_state, colspec, timestamp, new_messages):
    # Only consider messages with no car identified
    relevant_messages = [m for m in new_messages if _message_is_relevant(m)]
    dc.messages = relevant_messages + dc.messages
    if relevant_messages:
        return [('messages', get_data(dc))]
    else:
        return []


def _message_is_relevant(m):
    has_no_car = len(m) < 5 or m[4] is None
    is_broken_driver_change = 'Driver change (' in m[2]
    return has_no_car and not is_broken_driver_change


def get_data(dc):
    return {'messages': dc.messages}
