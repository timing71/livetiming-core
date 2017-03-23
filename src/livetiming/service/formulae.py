from livetiming.service.alkamel import Service as AlkamelService
from livetiming.analysis.laptimes import LapChart


class Service(AlkamelService):
    def __init__(self, config):
        super(Service, self).__init__(config, feed='formulae')

    def getAnalysisModules(self):
        return [
            LapChart
        ]
