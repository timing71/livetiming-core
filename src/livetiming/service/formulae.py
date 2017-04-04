from livetiming.analysis.laptimes import LapChart
from livetiming.service.alkamel import Service as AlkamelService


class Service(AlkamelService):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args, feed='formulae')

    def getAnalysisModules(self):
        return [
            LapChart
        ]
