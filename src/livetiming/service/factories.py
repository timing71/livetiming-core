from autobahn.twisted.websocket import WebSocketClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

from .version import USER_AGENT

import time


class Watchdog(object):
    def __init__(self, timeout, action_method, *action_args, **action_kwargs):
        self.log = Logger()
        self._timeout = timeout
        self._action_method = action_method
        self._action_args = action_args
        self._action_kwargs = action_kwargs
        self._call = LoopingCall(self._perform_check)

    def start(self):
        self._last_measure = time.time()
        self._call.start(self._timeout / 2, False)

    def stop(self):
        if self._call.running:
            self._call.stop()

    def notify(self):
        self._last_measure = time.time()

    def _perform_check(self):
        delta = time.time() - self._last_measure
        if delta > self._timeout:
            self.log.warn('WATCHDOG: {delta} since last notify received, triggering watchdog action', delta=delta)
            self._action_method(*self._action_args, **self._action_kwargs)


class ReconnectingWebSocketClientFactory(WebSocketClientFactory, ReconnectingClientFactory):
    log = Logger()
    maxDelay = 30

    def __init__(self, url, **kwargs):
        if 'useragent' not in kwargs:
            kwargs['useragent'] = USER_AGENT
        super().__init__(url, **kwargs)

    def clientConnectionFailed(self, connector, reason):
        self.log.warn("Connection to upstream source failed! Reason: {reason}. Retrying...", reason=reason)
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        self.log.warn("Connection to upstream source lost! Reason: {reason}. Retrying...", reason=reason)
        self.retry(connector)
