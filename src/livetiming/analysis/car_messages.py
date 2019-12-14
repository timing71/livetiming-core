from livetiming.racing import Stat


def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp, new_messages):
    car = dc.car(race_num)
    relevant_messages = [m for m in new_messages if _message_is_relevant(race_num, m)]
    car.messages += relevant_messages

    if len(relevant_messages) > 0:
        return (
            'car_messages/{}'.format(race_num),
            {
                race_num: car.messages
            }
        )
    return []


def _message_is_relevant(race_num, message):

    race_num_match = len(message) > 4 and \
        str(message[4]) == str(race_num)

    return race_num_match and message[3] != 'pit' and message[3] != 'out'


def get_data(dc):
    return {car.race_num: car.messages for car in list(dc._cars.values())}
