from livetiming.service.wige import Service as wige


class Service(wige):
    attribution = ['wige Solutions / GPSauge']

    def __init__(self, args, extra_args):
        extra_args.append('-e')
        extra_args.append('20')
        extra_args.append('--nurburgring')
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return 'VLN'
