from livetiming.service.alkamel import Service as AlkamelService


class Service(AlkamelService):
    def __init__(self, args, extra_args):
        extra_args.append('--disable-class-column')  # Class is populated but meaningless for FE
        super(Service, self).__init__(args, extra_args, feed='formulae')
