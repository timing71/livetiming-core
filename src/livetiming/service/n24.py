# -*- coding: utf-8 -*-

from livetiming.service.wige import Service as wige


class Service(wige):
    attribution = ['wige Solutions / GPSauge']

    def __init__(self, args, extra_args):
        extra_args.append('-e')
        extra_args.append('50')
        extra_args.append('--nurburgring')
        extra_args.append('--gpsauge')
        extra_args.append('IPHADAC24H')
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return 'Nurburgring 24 Hours'
