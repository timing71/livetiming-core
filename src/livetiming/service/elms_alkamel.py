from livetiming.service.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, config):
        super(Service, self).__init__(config, "41047e3e-c15e-53a1-9007-g1c3bc850710")

    def getName(self):
        return "ELMS"
