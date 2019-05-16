from livetiming.service.swisstiming import Service as SwissTimingService


class Service(SwissTimingService):
    attribution = ['ADAC / SportResult', 'https://www.adac.de/']
    namespace = 'RAC_PROD'
    profile = 'ADAC'
    default_name = 'ADAC GT Masters'
