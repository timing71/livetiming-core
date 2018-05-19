from livetiming.service.swisstiming import Service as SwissTimingService


class Service(SwissTimingService):
    attribution = ['Blancpain / SRO', 'https://www.blancpain-gt-series.com/']
    URL_BASE = "http://livecache.sportresult.com/node/db/RAC_PROD/SRO_2018_"
    default_name = 'Blancpain GT Series'
