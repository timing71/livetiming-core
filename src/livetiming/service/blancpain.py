from livetiming.service.swisstiming import Service as SwissTimingService

import time


class Service(SwissTimingService):
    attribution = ['Blancpain / SRO', 'https://www.blancpain-gt-series.com/']
    URL_BASE = "http://livecache.sportresult.com/node/db/RAC_PROD/SRO_{year}_".format(year=time.strftime("%Y"))
    default_name = 'Blancpain GT Series'
