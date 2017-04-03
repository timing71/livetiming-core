# -*- coding: utf-8 -*-
from livetiming.service.lemansseries import Service as LMS


class Service(LMS):
    def __init__(self, args, extra_args):
        LMS.__init__(self, args, extra_args)

    def getName(self):
        return "GT3 Le Mans Cup"

    def getStaticDataUrl(self):
        return "http://www.gt3lemanscup.com/en/live"

    def getRawFeedDataUrl(self):
        return "http://www.gt3lemanscup.com/assets/1/live/GT3/data.js?tx={}&t={}"
