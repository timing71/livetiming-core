from livetiming.service import Service as lt_service
from socketIO_client import SocketIO, BaseNamespace
from threading import Thread

import simplejson


def AlkamelNamespaceFactory(feedID, handler):
    class AlkamelNamespace(BaseNamespace):
        def on_connect(self, *args):
            self.emit('st', {"feed": feedID, "ver": "1.0"})

        def on_stOK(self, data):
            features = simplejson.loads(data)["features"]
            if features['timing'] == '1':
                self.emit('subscribe', 't')  # Timing
            if features['meteo'] == '1':
                self.emit('subscribe', 'm')  # Weather

        def on_st_refresh(self, data):
            handler.st_refresh(simplejson.loads(data))

        def on_st_update(self, data):
            handler.st_update(simplejson.loads(data))

        def on_meteo(self, data):
            handler.meteo(simplejson.loads(data))

        def on_session(self, data):
            handler.session(simplejson.loads(data))

        def on_rc_message(self, data):
            handler.rc_message(simplejson.loads(data))

    return AlkamelNamespace


class Service(lt_service):
    def __init__(self, config):
        lt_service.__init__(self, config)
        self.socketIO = SocketIO(
            'livetiming.alkamelsystems.com',
            80,
            AlkamelNamespaceFactory("92200890-f282-11e3-ac10-0800200c9a66", self)
        )
        socketThread = Thread(target=self.socketIO.wait)
        socketThread.daemon = True
        socketThread.start()

    def session(self, data):
        print data

    def st_refresh(self, data):
        print data

    def meteo(self, data):
        print data

    def rc_message(self, data):
        print data
