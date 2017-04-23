from livetiming.service.timeservice_nl import Service as tsnl_service


class Service(tsnl_service):

    def getHost(self):
        return "livetiming.tracktime.info"
