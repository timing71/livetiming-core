from livetiming.service.alkamel import Service as alkamel_service


class Service(alkamel_service):
    def __init__(self, args, extra_args):
        extra_args.append('--caution')
        super(Service, self).__init__(args, extra_args, feed="imsa")
