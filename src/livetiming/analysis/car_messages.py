from livetiming.racing import Stat
from livetiming.analysis import per_car


@per_car('car_messages', get_data)
def receive_state_update(dc, race_num, position, old_car, new_car, f, flag, timestamp, new_messages):
    car = dc.car(race_num)
    relevant_messages = [m for m in new_messages if _message_is_relevant(race_num, m)]
    car.messages += relevant_messages
    return len(relevant_messages) > 0


def _message_is_relevant(race_num, message):
    return len(message) > 4 and \
        message[4] == race_num and \
        message[3] != 'pit' and message[3] != 'out'


def get_data(dc):
    return {car.race_num: car.messages for car in list(dc._cars.values())}
