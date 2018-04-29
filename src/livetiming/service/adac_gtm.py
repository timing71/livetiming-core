from livetiming.service.sportresult import Service as SportResultService


class Service(SportResultService):
    attribution = ['ADAC / SportResult', 'https://www.adac.de/']
    URL_BASE = "http://livecache.sportresult.com/node/db/RAC_PROD/ADAC_2018_"
