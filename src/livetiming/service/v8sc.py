from livetiming.service.natsoft import Service as NatsoftService


class Service(NatsoftService):
    attribution = ['Supercars / Natsoft', 'http://racing.natsoft.com.au']

    def getName(self):
        return 'Virgin Australia Supercars'

    def getDefaultUrl(self):
        return 'http://timing.v8supercars.com.au:8080/LiveMeeting/V8SUPER'
