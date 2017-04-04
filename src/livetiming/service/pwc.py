from livetiming.analysis.driver import StintLength
from livetiming.analysis.laptimes import LapChart
from livetiming.service.tsl import Service as tsl_service


class Service(tsl_service):
    def getHost(self):
        return "lt-us.tsl-timing.com"

    def getSessionID(self):
        return 171006

    def getAnalysisModules(self):
        return [
            LapChart,
            StintLength
        ]
