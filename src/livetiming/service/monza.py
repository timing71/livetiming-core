from livetiming.service.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, config):
        super(Service, self).__init__(config, feed="4d74d480-0ddf-11e6-a148-3e1d05defe78")

    def getName(self):
        return "Monza"
