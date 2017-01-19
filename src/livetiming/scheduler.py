from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming.network import Realm, RPC
from os import environ
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import datetime
import icalendar
import re
import urllib2


EVT_SERVICE_REGEX = re.compile("(?P<name>[^\[]+) *\[(?P<service>[^*,\]]+)(,(?P<args>[^\]]+))?\]")


class Event(object):

    def __init__(self, uid, name, service, serviceArgs, startDate, endDate):
        self.uid = uid
        self.name = name
        self.service = service
        self.serviceArgs = serviceArgs
        self.startDate = startDate
        self.endDate = endDate

    def __repr__(self, *args, **kwargs):
        return "Event: {} (Service: {} {}) {} - {} [{}]".format(
            self.name,
            self.service,
            self.serviceArgs,
            self.startDate,
            self.endDate,
            self.uid
        )

    @staticmethod
    def from_ical(evt):
        uid = evt["UID"]
        summary = evt["SUMMARY"]
        startDate = evt.decoded("DTSTART")
        endDate = evt.decoded("DTEND")

        match = EVT_SERVICE_REGEX.match(summary)
        if match:
            return Event(
                uid,
                match.group("name"),
                match.group("service"),
                match.group("args").split(" ") if match.group("args") else [],
                startDate,
                endDate
            )
        else:
            print "Incorrect event format: {}".format(summary)


class Scheduler(ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.events = {}
        self.calendarAddress = environ['LIVETIMING_CALENDAR_URL']

    def listSchedule(self):
        return {}  # TODO Stub

    def updateSchedule(self):
        self.log.info("Syncing schedule with Google Calendar...")
        ics = urllib2.urlopen(self.calendarAddress).read()
        cal = icalendar.Calendar.from_ical(ics)

        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)

        self.events.clear()

        for evt in cal.subcomponents:
            evtEnd = evt.decoded("DTEND").replace(tzinfo=None)
            if evtEnd > cutoff:
                e = Event.from_ical(evt)
                if e:
                    self.events[e.uid] = e
                    print "Found event: {}".format(e)

        self.log.info("Sync complete")

    def execute(self):
        pass  # TODO Stub

    @inlineCallbacks
    def onJoin(self, details):
        self.log.info("Session ready")

        yield self.register(self.listSchedule, RPC.SCHEDULE_LISTING)
        self.log.debug("Registered service listing RPC")

        update = task.LoopingCall(self.updateSchedule)
        update.start(600)  # Update from Google Calendar every 10 minutes

        execute = task.LoopingCall(self.execute)
        execute.start(60)  # Start and stop services every minute

    def onDisconnect(self):
        self.log.info("Disconnected")
        if reactor.running:
            reactor.stop()


def main():
    Logger().info("Starting scheduler service...")
    router = unicode(environ.get("LIVETIMING_ROUTER", u"ws://crossbar:8080/ws"))
    runner = ApplicationRunner(url=router, realm=Realm.TIMING)
    runner.run(Scheduler)


if __name__ == '__main__':
    main()
