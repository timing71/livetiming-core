from livetiming.service.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args, feed="monza")
