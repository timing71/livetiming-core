from livetiming.service.wec import Service as WECService


class Service(WECService):
    attribution = ['WEC / ACO', 'http://www.fiawec.com/']
    initial_description = ''

    def getName(self):
        return "Le Mans 24 Hours"
