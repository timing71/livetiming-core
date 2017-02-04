from .timeservice_nl import Service as TSNLService


class Service(TSNLService):
    def getName(self):
        return "24H Series"

    def getTrackID(self):
        return "17047960b73e48c4a899f43a2459cc20"
