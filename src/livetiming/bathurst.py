from .timeservice_nl import Service as TSNLService


class Service(TSNLService):
    def getName(self):
        return "Bathurst"

    def getTrackID(self):
        return "59225c5480a74b178deaf992976595c3"
