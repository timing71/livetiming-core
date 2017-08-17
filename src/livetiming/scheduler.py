from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from autobahn.wamp.types import RegisterOptions
from livetiming import servicemanager, load_env, sentry
from livetiming.network import Realm, RPC, Channel, Message, MessageClass, authenticatedService
from threading import Lock
from twisted.internet import task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import datetime
import icalendar
import re
import os
import pytz
import urllib2
import time


EVT_SERVICE_REGEX = re.compile("(?P<name>[^\[]+[^ ]) ?\[(?P<service>[^*,\]]+)(, ?(?P<args>[^\]]+))?\]")

EVENT_START_BUFFER = datetime.timedelta(minutes=5)  # Start this many minutes early
EVENT_END_BUFFER = datetime.timedelta(minutes=10)  # Overrun by this much


sentry = sentry()


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


def create_scheduler_session(scheduler):
    class SchedulerSession(ApplicationSession):
        @inlineCallbacks
        def onJoin(self, details):
            scheduler.log.info("Scheduler session ready")

            yield self.register(scheduler.listSchedule, RPC.SCHEDULE_LISTING, RegisterOptions(force_reregister=True))
            scheduler.log.debug("Registered service listing RPC")

            scheduler.set_publish(self.publish)

        def onDisconnect(self):
            scheduler.log.info("Disconnected from live timing service")
            scheduler.set_publish(None)

    return authenticatedService(SchedulerSession)


class Scheduler(object):
    log = Logger()

    def __init__(self):
        self.events = {}
        self.runningEvents = []
        self.calendarAddress = os.environ['LIVETIMING_CALENDAR_URL']
        self.lock = Lock()
        self._publish = None

    def start(self):
        update = task.LoopingCall(self.updateSchedule)
        update.start(600)  # Update from Google Calendar every 10 minutes

        execute = task.LoopingCall(self.execute)
        execute.start(60)  # Start and stop services every minute

        session_class = create_scheduler_session(self)
        router = unicode(os.environ["LIVETIMING_ROUTER"])
        runner = ApplicationRunner(url=router, realm=Realm.TIMING)
        runner.run(session_class, auto_reconnect=True)
        self.log.info("Scheduler terminated.")

    def listSchedule(self):
        now = datetime.datetime.now(pytz.utc)
        upcoming = [j for j in self.events.values() if j.startDate > now and j.uid not in self.runningEvents]
        return map(lambda j: j.serialize(), upcoming)

    def updateSchedule(self):
        with self.lock:
            self.log.info("Syncing schedule with Google Calendar...")
            try:
                ics = urllib2.urlopen(self.calendarAddress).read()
                cal = icalendar.Calendar.from_ical(ics)

                cutoff = datetime.datetime.now(pytz.utc) - EVENT_END_BUFFER - datetime.timedelta(seconds=60)

                self.events.clear()

                for evt in cal.subcomponents:
                    evtEnd = evt.decoded("DTEND")
                    if evtEnd > cutoff:
                        e = Event.from_ical(evt, self.log)
                        if e:
                            self.events[e.uid] = e
                            print "Found event: {}".format(e)

                self.log.info("Sync complete")
            except Exception:
                self.log.failure("Exception while syncing calendar: {log_failure}")
                sentry.captureException()
        self.publish(Channel.CONTROL, Message(MessageClass.SCHEDULE_LISTING, self.listSchedule()).serialise())

    def execute(self):
        with self.lock:
            self.log.debug("Running scheduler loop...")

            now = datetime.datetime.now(pytz.utc)
            poll_interval = datetime.timedelta(seconds=60)

            cutoff_start = now + EVENT_START_BUFFER + poll_interval
            cutoff_end = now - EVENT_END_BUFFER

            toStart = [j for j in self.events.values() if j.startDate < cutoff_start and j.endDate > now and j.uid not in self.runningEvents]
            toEnd = [j for j in self.events.values() if j.endDate < cutoff_end]

            hasChanged = False

            for job in toStart:
                try:
                    self._start_service(job.uid, job.service, job.serviceArgs)
                    hasChanged = True
                except Exception:
                    self.log.failure("Exception while starting job: {log_failure}")
                    sentry.captureException()

            for job in toEnd:
                try:
                    self._stop_service(job.uid, job.service)
                    hasChanged = True
                except Exception:
                    self.log.failure("Exception while stopping job: {log_failure}")
                    sentry.captureException()

        if hasChanged:
            self.publish(Channel.CONTROL, Message(MessageClass.SCHEDULE_LISTING, self.listSchedule()).serialise())

        self.log.debug("Scheduler loop complete")

    def set_publish(self, func):
        self._publish = func

    def publish(self, *args):
        if self._publish:
            self._publish(*args)
        else:
            self.log.debug("Call to publish with no publish function set!")

    def _start_service(self, uid, service, args):
        self.log.info("Starting service {} with args {}".format(service, args))
        servicemanager.start_service(service, args)
        self.runningEvents.append(uid)

    def _stop_service(self, uid, service):
        self.log.info("Stopping service {}".format(service))
        servicemanager.stop_service(service)
        self.runningEvents.remove(uid)
        self.events.pop(uid)


def main():
    load_env()
    Logger().info("Starting scheduler service...")
    scheduler = Scheduler()
    scheduler.start()


if __name__ == '__main__':
    main()
