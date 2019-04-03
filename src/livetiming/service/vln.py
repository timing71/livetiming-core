from livetiming.service.wige import Service as wige


class Service(wige):
    def __init__(self, args, extra_args):
        extra_args.append('--ws')
        extra_args.append('wss://livetiming.azurewebsites.net/event-20/ws')
        extra_args.append('-e')
        extra_args.append('20')
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return 'VLN'
