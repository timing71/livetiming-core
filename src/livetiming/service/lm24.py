from livetiming.service.wec_unified import Service as WECService


class Service(WECService):
    attribution = ['WEC / ACO', 'http://www.fiawec.com/']
    initial_description = ''

    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return "Le Mans 24 Hours"
