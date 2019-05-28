from livetiming.service.swisstiming import Service as SwissTimingService

import time


class Service(SwissTimingService):
    attribution = ['Blancpain / SRO', 'https://www.blancpain-gt-series.com/']
    namespace = 'RAC_PROD'
    profile = 'SRO'
    default_name = 'Blancpain GT Series'
