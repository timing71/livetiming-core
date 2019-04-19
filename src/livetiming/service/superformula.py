from livetiming.service.racenow import Service as RaceNowService


class Service(RaceNowService):
    def __init__(self, args, extra_args):
        extra_args.append('--ws')
        extra_args.append('ws://superformula.racelive.jp:8001/get')
        super(Service, self).__init__(args, extra_args)

    def getName(self):
        return 'Super Formula'
