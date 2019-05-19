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
        return 'Nürburgring 24 Hours'

    def getDefaultDescription(self):
        return u'{} - {}'.format(
            self._data.get('CUP', ''),
            self._data.get('HEAT', '')
        )
