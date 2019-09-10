from twisted.internet import reactor
from twisted.logger import Logger
from twisted.web import client

import simplejson

client.HTTPClientFactory.noisy = False
client._HTTP11ClientFactory.noisy = False


class Fetcher(object):
    log = Logger()

    def __init__(self, url, callback, interval):
        self.url = url
        self.callback = callback
        self.interval = interval

        self.backoff = 0
        self.running = False

    def _schedule(self, delay):
        if self.running:
            reactor.callLater(delay, self._run)

    def _defer(self):
        if callable(self.url):
            url = self.url()
        else:
            url = self.url

        try:
            return client.getPage(url)
        except Exception as e:
            self.log.failure("URL {url} returned error: {msg}", url=url, msg=str(e))
            raise

    def _run(self):
        if self.running:
            def cb(data):
                self.backoff = 0
                if self.running:
                    self.callback(data)
                    self._schedule(self.interval)

            def eb(fail):
                if self.running:
                    self.backoff = max(1, self.backoff * 2)
                    self.log.warn("Fetcher failed: {fail}. Trying again in {backoff} seconds", fail=fail, backoff=self.backoff)
                    self._schedule(self.backoff)

            deferred = self._defer()
            deferred.addCallback(cb)
            deferred.addErrback(eb)

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
        except simplejson.dumpJSONDecodeError:
            Logger().failure("Error parsing JSON from source {url}: {log_failure}. Full source was {source}", url=url, source=data)
    return Fetcher(url, parse_then_callback, interval)


def MultiLineFetcher(url, callback, interval):
    return Fetcher(url, lambda l: callback(l.splitlines()), interval)
