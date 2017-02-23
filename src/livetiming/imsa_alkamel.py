from livetiming.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, config):
        super(Service, self).__init__(config, feed="910a7e3e-x15e-93a1-1007-r8c7xa149609")

    def getName(self):
        return "IMSA"
