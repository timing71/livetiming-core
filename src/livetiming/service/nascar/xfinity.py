from livetiming.service.nascar import Service as nascar_service


class Service(nascar_service):

    def getSeriesTag(self):
        return "nxs-"
