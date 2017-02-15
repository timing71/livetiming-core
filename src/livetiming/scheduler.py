from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from livetiming import servicemanager
from livetiming.network import Realm, RPC, Channel, Message, MessageClass,\
    AuthenticatedService
from os import environ
from threading import Lock
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import datetime
import icalendar
import re
import pytz
import urllib2
import time


EVT_SERVICE_REGEX = re.compile("(?P<name>[^\[]+[^ ]) ?\[(?P<service>[^*,\]]+)(,(?P<args>[^\]]+))?\]")


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
    def from_ical(evt, logger=None):
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
            if logger:
                logger.warn("Incorrect event format: {}".format(summary))
            else:
                print "Incorrect event format: {}".format(summary)

    def serialize(self):
        return {
            "id": self.uid,
            "name": self.name,
            "startTime": time.mktime(self.startDate.utctimetuple())
        }


class Scheduler(AuthenticatedService, ApplicationSession):
    log = Logger()

    def __init__(self, config):
        ApplicationSession.__init__(self, config)
        self.events = {}
        self.runningEvents = []
        self.calendarAddress = environ['LIVETIMING_CALENDAR_URL']
        self.lock = Lock()

    def listSchedule(self):
        now = datetime.datetime.now(pytz.utc)
        upcoming = [j for j in self.events.values() if j.startDate > now and j.uid not in self.runningEvents]
        return map(lambda j: j.serialize(), upcoming)

    def updateSchedule(self):
        with self.lock:
            self.log.info("Syncing schedule with Google Calendar...")
            ics = urllib2.urlopen(self.calendarAddress).read()
            cal = icalendar.Calendar.from_ical(ics)

            cutoff = datetime.datetime.now(pytz.utc) - datetime.timedelta(seconds=60)

            self.events.clear()

            for evt in cal.subcomponents:
                evtEnd = evt.decoded("DTEND")
                if evtEnd > cutoff:
                    e = Event.from_ical(evt, self.log)
                    if e:
                        self.events[e.uid] = e
                        print "Found event: {}".format(e)

            self.log.info("Sync complete")
        self.publish(Channel.CONTROL, Message(MessageClass.SCHEDULE_LISTING, self.listSchedule()).serialise())

    def execute(self):
        with self.lock:
            self.log.debug("Running scheduler loop...")

            now = datetime.datetime.now(pytz.utc)
            cutoff = now + datetime.timedelta(seconds=60)
            toStart = [j for j in self.events.values() if j.startDate < cutoff and j.endDate > now and j.uid not in self.runningEvents]
            toEnd = [j for j in self.events.values() if j.endDate < cutoff]

            hasChanged = False

            for job in toStart:
                try:
                    self.log.info("Starting service {} with args {}".format(job.service, job.serviceArgs))
                    servicemanager.start_service(job.service, job.serviceArgs)
                    self.runningEvents.append(job.uid)
                    hasChanged = True
                except Exception as e:
                    self.log.critical(e)

            for job in toEnd:
                try:
                    self.log.info("Stopping service {}".format(job.service))
                    servicemanager.stop_service(job.service)
                    self.runningEvents.remove(job.uid)
                    self.events.pop(job.uid)
                    hasChanged = True
                except Exception as e:
                    self.log.critical(str(e))

        if hasChanged:
            self.publish(Channel.CONTROL, Message(MessageClass.SCHEDULE_LISTING, self.listSchedule()).serialise())

        self.log.debug("Scheduler loop complete")

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
