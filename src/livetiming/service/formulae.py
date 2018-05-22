from livetiming.service.alkamel2 import Service as AlkamelService


class Service(AlkamelService):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args, feed='fiaformulae')
