# import socketio

# sio = socketio.Client(logger=True)


# def printy_callback(*args):
#     print args


# @sio.on('connect')
# def on_connect():
#     print 'Connected'


# @sio.on('ready')
# def on_ready():
#     #sio.send('"0000000069{"compressor":0,"format":"json","type":"clientinfo","app":"RAC_PROD"}{"frontendIdentifier":"racResults"}"')
#     sio.emit('join', 'RAC_PROD|SRO_2019_GLOBAL_DATA_JSON', callback=printy_callback)
#     sio.emit('join', 'RAC_PROD|SRO_SEASONS_JSON', callback=printy_callback)
#     sio.emit('join', 'RAC_PROD|SRO_2019_SEASON_JSON', callback=printy_callback)


# @sio.on('message')
# def on_message(data):
#     print 'Message', data

# sio.connect(
#     'https://livestats-lb.sportresult.com',
#     transports=['websocket']
# )

# sio.wait()

from livetiming.service.swisstiming.client import Client
from twisted.internet import reactor

c = Client('RAC_PROD', 'SRO')
c.start()
reactor.run()
