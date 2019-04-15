from livetiming.service.timeservice_nl import Service as TSNLService


class Service(TSNLService):
    def __init__(self, args, extra_args):
        if '--tk' not in extra_args:
            extra_args.append('--tk')
            extra_args.append('bathurst')
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return "Bathurst"
