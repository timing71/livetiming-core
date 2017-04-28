from livetiming.analysis.driver import StintLength
from livetiming.analysis.laptimes import LaptimeChart
from livetiming.service.tsl import Service as tsl_service


class Service(tsl_service):
    def getHost(self):
        return "lt-us.tsl-timing.com"

    def getAnalysisModules(self):
        return [
            LaptimeChart,
            StintLength
        ]
