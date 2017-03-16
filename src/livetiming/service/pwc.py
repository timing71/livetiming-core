from livetiming.service.tsl import Service as tsl_service
from livetiming.analysis.laptimes import LaptimeAnalysis
from livetiming.analysis.driver import StintLength


class Service(tsl_service):
    def getHost(self):
        return "lt-us.tsl-timing.com"

    def getSessionID(self):
        return 171006

    def getAnalysisModules(self):
        return [
            LaptimeAnalysis,
            StintLength
        ]
