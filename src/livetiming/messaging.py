from enum import Enum


class Realm:
    TIMING = u'timing'


class Channel:
    CONTROL = u'livetiming.control'


class MessageClass(Enum):
    INITIALISE_DIRECTORY = 1
    SERVICE_REGISTRATION = 2
    SERVICE_DEREGISTRATION = 3


class Message(object):

    def __init__(self, msgClass, payload=None):
        self.msgClass = msgClass
        self.payload = payload

    def serialise(self):
        return {
            'msgClass': self.msgClass.value,
            'payload': self.payload
        }

    @staticmethod
    def parse(rawMsg):
        return Message(MessageClass(rawMsg['msgClass']), rawMsg['payload'])

    def __str__(self):
        return "<Message class={0} payload={1}>".format(self.msgClass, self.payload)
