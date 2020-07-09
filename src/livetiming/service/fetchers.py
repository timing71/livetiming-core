from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.logger import Logger
from twisted.web.client import Agent, readBody, _HTTP11ClientFactory

import simplejson


_HTTP11ClientFactory.noisy = False


class Fetcher(object):
    log = Logger()

    def __init__(self, url, callback, interval):
        self.url = url
        self.callback = callback
        self.interval = interval

        self._agent = Agent(reactor)

        self.backoff = 0
        self.running = False

    def _schedule(self, delay):
        if self.running:
            reactor.callLater(delay, self._run)

    @inlineCallbacks
    def _run(self):
        if self.running:
            try:
                if callable(self.url):
                    url = self.url()
                else:
                    url = self.url

                response = yield self._agent.request(
                    b'GET',
                    url
                )
                body = yield readBody(response)
                self.backoff = 0
                if self.running:
                    self.callback(body)
                    self._schedule(self.interval)
            except Exception as fail:
                if self.running:
                    self.backoff = max(1, self.backoff * 2)
                    self.log.warn("Fetcher failed: {fail}. Trying again in {backoff} seconds", fail=fail, backoff=self.backoff)
                    self._schedule(self.backoff)

    def start(self):
        self.running = True
        self._run()

    def stop(self):
        self.running = False


def JSONFetcher(url, callback, interval):
    def parse_then_callback(data):
        try:
            parsed_data = simplejson.loads(data)
            callback(parsed_data)
        except simplejson.JSONDecodeError:
            Logger().failure("Error parsing JSON from source {url}: {log_failure}. Full source was {source}", url=url, source=data)
    return Fetcher(url, parse_then_callback, interval)


def MultiLineFetcher(url, callback, interval):
    return Fetcher(url, lambda l: callback(l.splitlines()), interval)
