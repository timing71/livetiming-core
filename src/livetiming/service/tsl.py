from livetiming.service import Service as lt_service
from requests.sessions import Session
from signalr import Connection
from signalr.hubs._hub import HubServer
from signalr.events._events import EventHook
from threading import Thread
from livetiming.racing import Stat


###################################
# BEGIN patches to signalr-client #
###################################
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


def fire(self, *args, **kwargs):
    # Remove any handlers that return False from calling them
    self._handlers = [h for h in self._handlers if h(*args, **kwargs) != False]

EventHook.fire = fire

###################################
#  END patches to signalr-client  #
###################################


class TSLClient(Thread):

    def __init__(self, handler, host="livetiming.tsl-timing.com", sessionID="WebDemo"):
        Thread.__init__(self)
        self.handler = handler
        self.log = handler.log
        self.host = host
        self.sessionID = sessionID
        self.daemon = True

    def run(self):
        with Session() as session:
            connection = Connection("http://{}/signalr/".format(self.host), session)
            hub = connection.register_hub('livetiming')

            def print_error(error):
                print('error: ', error)

            def delegate(method, data):
                handler_method = "on_{}".format(method.lower())
                if hasattr(self.handler, handler_method) and callable(getattr(self.handler, handler_method)):
                    getattr(self.handler, handler_method)(data)
                else:
                    self.log.info("Unhandled message: {}".format(handler_method))
                    self.log.debug("Message content was {}".format(data))

            def handle(**kwargs):
                if 'M' in kwargs:
                    for msg in kwargs['M']:
                        delegate(msg['M'], msg['A'])

            connection.error += print_error
            connection.received += handle

            with connection:
                hub.server.invoke('RegisterConnectionId', self.sessionID, True, False, True)
                hub.server.invoke_then('GetClassification', self.sessionID)(lambda d: delegate('classification', d))
                hub.server.invoke_then('GetSessionData', self.sessionID)(lambda d: delegate('session', d))

                connection.wait(None)


class Service(lt_service):
    def __init__(self, config):
        super(Service, self).__init__(config)
        client = TSLClient(self, host="lt-us.tsl-timing.com", sessionID="171006")
        client.start()

        self.name = "TSL Timing"
        self.description = ""

    def getHost(self):
        return "livetiming.tsl-timing.com"

    def getSessionID(self):
        return "WebDemo"

    def getColumnSpec(self):
        return [
            Stat.NUM,
            Stat.CLASS,
            Stat.STATE,
            Stat.DRIVER,
            Stat.CAR,
            Stat.LAPS,
            Stat.GAP,
            Stat.INT,
            Stat.S1,
            Stat.S2,
            Stat.S3,
            Stat.LAST_LAP,
            Stat.BEST_LAP
        ]

    def getName(self):
        return self.name

    def getDefaultDescription(self):
        return self.description

    def getRaceState(self):
        return {
            "cars": [],
            "session": {
                "flagState": "none",
                "timeElapsed": 0,
                "timeRemain": -1
            }
        }

    def on_session(self, data):
        if "TrackDisplayName" in data:
            self.name = data["TrackDisplayName"]
        if "Series" in data and "Name" in data:
            if data["Series"] and data["Name"]:
                self.description = "{} - {}".format(data["Series"], data["Name"])
            elif data["Series"]:
                self.description = data["Series"]
            elif data["Name"]:
                self.description = data["Name"]
        print data
        self.publishManifest()
