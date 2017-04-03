# -*- coding: utf-8 -*-
from livetiming.service.lemansseries import Service as LMS


class Service(LMS):
    def __init__(self, args, extra_args):
        LMS.__init__(self, args, extra_args)

    def getName(self):
        return "European Le Mans Series"

    def getStaticDataUrl(self):
        return "http://www.europeanlemansseries.com/en/live"

    def getRawFeedDataUrl(self):
        return "http://www.europeanlemansseries.com/assets/1/live/ELMS/data.js?tx={}&t={}"
