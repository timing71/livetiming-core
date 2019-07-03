from .alkamel2 import Service as AlKamelService


class Service(AlKamelService):
    def __init__(self, args, extra_args):
        super(Service, self).__init__(args, extra_args, feed="imsa")
