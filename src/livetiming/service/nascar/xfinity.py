from livetiming.service.nascar import Service as nascar_service
import random


class Service(nascar_service):

    def getFeedURL(self):
        return "http://www.nascar.com/live/feeds/series_2/4617/live_feed.json?del={}".format(random.randint(1, 1024))
