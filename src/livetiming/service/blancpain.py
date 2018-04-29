from livetiming.service.sportresult import Service as SportResultService


class Service(SportResultService):
    attribution = ['Blancpain / SRO', 'https://www.blancpain-gt-series.com/']
    URL_BASE = "http://livecache.sportresult.com/node/db/RAC_PROD/SRO_2018_"
