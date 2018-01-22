# -*- coding: utf-8 -*-
from livetiming.service.lemansseries import Service as LMS


class Service(LMS):
    attribution = ['ELMS', 'http://www.lemanscup.com/']

    def __init__(self, args, extra_args):
        LMS.__init__(self, args, extra_args)

    def getName(self):
        return "Le Mans Cup"

    def getStaticDataUrl(self):
        return "http://www.lemanscup.com/en/live"

    def getRawFeedDataUrl(self):
        return "http://www.lemanscup.com/ecm/live/LMC/data.js?tx={}&t={}"
