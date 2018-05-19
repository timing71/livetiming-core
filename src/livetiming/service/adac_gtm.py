from livetiming.service.swisstiming import Service as SwissTimingService


class Service(SwissTimingService):
    attribution = ['ADAC / SportResult', 'https://www.adac.de/']
    URL_BASE = "http://livecache.sportresult.com/node/db/RAC_PROD/ADAC_2018_"
    default_name = 'ADAC GT Masters'
