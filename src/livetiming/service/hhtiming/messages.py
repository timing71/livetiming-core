from livetiming.messages import TimingMessage, CAR_NUMBER_REGEX

import time


class RaceControlMessage(TimingMessage):

    def __init__(self, protocol):
        self.protocol = protocol
        self._messageIndex = 0

    def process(self, _, __):

        new_messages = self.protocol.messages[self._messageIndex:]

        msgs = []

        for msg in sorted(new_messages, key=lambda m: m[0]):
            hasCarNum = CAR_NUMBER_REGEX.search(msg[1])
            msgDate = time.time() * 1000
            if hasCarNum:
                msgs.append([msgDate / 1000, "Race Control", msg[1].upper(), "raceControl", hasCarNum.group('race_num')])
            else:
                msgs.append([msgDate / 1000, "Race Control", msg[1].upper(), "raceControl"])

            self._messageIndex = len(self.protocol.messages)
        return sorted(msgs, key=lambda m: -m[0])
