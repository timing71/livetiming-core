# -*- coding: utf-8 -*-
from livetiming.lemansseries import Service as LMS


class Service(LMS):
    def __init__(self, config):
        LMS.__init__(self, config)

    def getName(self):
        return "European Le Mans Series"

    def getStaticDataUrl(self):
        return "http://www.europeanlemansseries.com/en/live"

    def getRawFeedDataUrl(self):
        return "http://www.europeanlemansseries.com/assets/1/live/ELMS/data.js?tx={}&t={}"
