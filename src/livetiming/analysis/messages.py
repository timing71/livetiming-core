def receive_state_update(dc, old_state, new_state, colspec, timestamp, new_messages):
    dc.messages = new_messages + dc.messages
    if new_messages:
        return [('messages', get_data(dc))]
    else:
        return []


def get_data(dc):
    return {'messages': dc.messages}
