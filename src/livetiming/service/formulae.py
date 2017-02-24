from livetiming.service.alkamel import Service as AlkamelService


class Service(AlkamelService):
    def __init__(self, config):
        super(Service, self).__init__(config, feed='92200890-f282-11e3-ac10-0800200c9a66')

    def getName(self):
        return "Formula E"
