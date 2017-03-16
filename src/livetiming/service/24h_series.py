from livetiming.service.timeservice_nl import Service as TSNLService


class Service(TSNLService):
    def getName(self):
        return "24H Series"
