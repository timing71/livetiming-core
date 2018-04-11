from livetiming.service.tsl import Service as tsl_service


class Service(tsl_service):
    def getName(self):
        return "Pirelli World Challenge"

    def getHost(self):
        return "lt-us.tsl-timing.com"
