from signalr.hubs._hub import HubServer
from signalr.events._events import EventHook


def patch_signalr():
    patch_hub_add_invoke_then()
    patch_eventhook_alter_fire()


def patch_hub_add_invoke_then():
    def invoke_then(self, method, *data):
        send_counter = self._HubServer__connection.increment_send_counter()

        def then(func):
            def onServerResponse(**kwargs):
                if 'I' in kwargs and int(kwargs['I']) == send_counter:
                        if 'R' in kwargs:
                            func(kwargs['R'])
                        return False
            self._HubServer__connection.received += onServerResponse

            self._HubServer__connection.send({
                'H': self.name,
                'M': method,
                'A': data,
                'I': send_counter
            })
        return then

    HubServer.invoke_then = invoke_then


def patch_eventhook_alter_fire():
    def fire(self, *args, **kwargs):
        # Remove any handlers that return False from calling them
        self._handlers = [h for h in self._handlers if h(*args, **kwargs) is not False]

    EventHook.fire = fire
