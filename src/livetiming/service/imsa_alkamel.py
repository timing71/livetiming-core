from livetiming.service.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, config):
        super(Service, self).__init__(config, feed="imsa")
