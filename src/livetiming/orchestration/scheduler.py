from autobahn.twisted.component import run
from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.types import PublishOptions
from collections import defaultdict
from livetiming import load_env, sentry, make_component
from livetiming.orchestration import servicemanager
from livetiming.network import Realm, RPC, Channel, Message, MessageClass, authenticatedService
from threading import Lock
from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks
from twisted.logger import Logger

import datetime
import icalendar
import re
import os
import pytz
import urllib
import sentry_sdk
import time
import twitter


EVT_SERVICE_REGEX = re.compile(r"(?P<name>[^\[]+[^ ]) ?\[(?P<service>[^*,\]]+)(, ?(?P<args>[^\]]+))?\]")

EVENT_START_BUFFER = datetime.timedelta(minutes=5)  # Start this many minutes early
EVENT_END_BUFFER = datetime.timedelta(minutes=10)  # Overrun by this much


sentry()


class Event(object):

    def __init__(self, uid, name, service, serviceArgs, startDate, endDate):
        self.uid = uid
        self.name = name
        self.service = service
        self.serviceArgs = serviceArgs
        self.startDate = startDate
        self.endDate = endDate

    def __repr__(self, *args, **kwargs):
        return "Event: {} (Service: {} {}) {} - {} [{}] {}".format(
            self.name,
            self.service,
            self.serviceArgs,
            self.startDate,
            self.endDate,
            self.uid,
            '(H)' if self.is_hidden() else ''
        ).strip()

    def is_hidden(self):
        return '--hidden' in self.serviceArgs or '-H' in self.serviceArgs

    @staticmethod
    def from_ical(evt, logger=None):
        uid = evt["UID"]
        summary = evt["SUMMARY"]
        startDate = evt.decoded("DTSTART")
        endDate = evt.decoded("DTEND")

        match = EVT_SERVICE_REGEX.match(summary)
        if match:

            if match.group('args'):
                processed_args = list(
                    map(
                        lambda a: a.replace(r'\ ', ' '),
                        re.split(r"(?<!\\) ", match.group('args'))
                    )
                )
            else:
                processed_args = []

            return Event(
                uid,
                match.group("name"),
                match.group("service"),
                processed_args,
                startDate,
                endDate
            )
        else:
            if logger:
                logger.warn("Incorrect event format: {}".format(summary))
            else:
                print("Incorrect event format: {}".format(summary))

    def serialize(self):
        return {
            "id": self.uid,
            "name": self.name,
            "startTime": time.mktime(self.startDate.utctimetuple()),
            "hidden": self.is_hidden()
        }


class Tweeter(object):

    EVENT_START_MESSAGE = "Starting now: {name}. Follow live at {link}"

    def __init__(self):
        self.log = Logger()
        self._twitter = None

        consumer_key = os.getenv("TWITTER_CONSUMER_KEY")
        consumer_secret = os.getenv("TWITTER_CONSUMER_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_secret = os.getenv("TWITTER_ACCESS_SECRET")

        if consumer_key and consumer_secret and access_token and access_secret:
            self._twitter = twitter.Api(
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                access_token_key=access_token,
                access_token_secret=access_secret
            )
        else:
            self.log.info("No Twitter credentials provided (or credentials incomplete), Twitter functionality disabled.")

    def _construct_message(self, template, event):
        if '-m' in event.serviceArgs:
            service_name = event.serviceArgs[event.serviceArgs.index('-m') + 1]
        elif '--masquerade' in event.serviceArgs:
            service_name = event.serviceArgs[event.serviceArgs.index('--masquerade') + 1]
        else:
            service_name = event.service
        return template.format(
            name=event.name,
            link="https://www.timing71.org/s/{}".format(service_name)
        )

    def tweet(self, text):
        if self._twitter:
            reactor.callInThread(self._twitter.PostUpdate, text)

    def tweet_event_starting(self, event):
        if not event.is_hidden():
            self.tweet(
                self._construct_message(
                    self.EVENT_START_MESSAGE,
                    event
                )
            )


def create_scheduler_session(scheduler):
    class SchedulerSession(ApplicationSession):
        def onJoin(self, details):
            scheduler.log.info("Scheduler session ready")
            scheduler.set_publish(self.publish)
            scheduler.publish_schedule()

        def onDisconnect(self):
            scheduler.log.info("Disconnected from live timing service")
            scheduler.set_publish(None)

    return authenticatedService(SchedulerSession)


class Scheduler(object):
    log = Logger()

    def __init__(self):
        self.events = {}
        self.runningEvents = []
        self.running_events_per_service = defaultdict(list)
        self.calendarAddress = os.environ['LIVETIMING_CALENDAR_URL']
        self.lock = Lock()
        self._publish = None
        self.publish_options = PublishOptions(retain=True)

        self._tweeter = Tweeter()

    def start(self):
        update = task.LoopingCall(self.updateSchedule)
        update.start(600)  # Update from Google Calendar every 10 minutes

        execute = task.LoopingCall(self.execute)
        execute.start(60)  # Start and stop services every minute

        session_class = create_scheduler_session(self)

        component = make_component(session_class)
        run(component)

        self.log.info("Scheduler terminated.")

    def listSchedule(self):
        now = datetime.datetime.now(pytz.utc)
        upcoming = [j for j in list(self.events.values()) if j.startDate > now and j.uid not in self.runningEvents]
        return [j.serialize() for j in upcoming]

    def updateSchedule(self):
        with self.lock:
            self.log.info("Syncing schedule with Google Calendar...")
            try:
                ics = urllib.request.urlopen(self.calendarAddress).read()
                cal = icalendar.Calendar.from_ical(ics)

                cutoff = datetime.datetime.now(pytz.utc) - EVENT_END_BUFFER - datetime.timedelta(seconds=60)

                self.events.clear()

                for evt in cal.subcomponents:
                    evtEnd = evt.decoded("DTEND")
                    if evtEnd > cutoff:
                        e = Event.from_ical(evt, self.log)
                        if e:
                            self.events[e.uid] = e
                            self.log.debug("Found event: {evt}", evt=e)

                self.log.info("Sync complete, {num} event(s) found", num=len(self.events))
            except Exception as e:
                self.log.failure("Exception while syncing calendar: {log_failure}")
                sentry_sdk.capture_exception(e)
        self.publish_schedule()

    def execute(self):
        with self.lock:
            self.log.debug("Running scheduler loop...")

            now = datetime.datetime.now(pytz.utc)
            poll_interval = datetime.timedelta(seconds=60)

            cutoff_start = now + EVENT_START_BUFFER + poll_interval
            cutoff_end = now - EVENT_END_BUFFER

            toStart = [j for j in list(self.events.values()) if j.startDate < cutoff_start and j.endDate > now and j.uid not in self.runningEvents]
            toEnd = [j for j in list(self.events.values()) if j.endDate < cutoff_end]

            hasChanged = False

            for job in toEnd:
                try:
                    self._stop_service(job.uid, job.service)
                    hasChanged = True
                except Exception as e:
                    self.log.failure("Exception while stopping job: {log_failure}")
                    sentry_sdk.capture_exception(e)

            for job in toStart:
                try:
                    self._start_service(job.uid, job.service, job.serviceArgs)
                    self._tweeter.tweet_event_starting(job)
                    hasChanged = True
                except Exception as e:
                    self.log.failure("Exception while starting job: {log_failure}")
                    sentry_sdk.capture_exception(e)

        if hasChanged:
            self.publish_schedule()

        self.log.debug("Scheduler loop complete")

    def publish_schedule(self):
        self.publish(
            Channel.SCHEDULER,
            Message(MessageClass.SCHEDULE_LISTING, self.listSchedule(), retain=True).serialise(),
            options=self.publish_options
        )

    def set_publish(self, func):
        self._publish = func

    def publish(self, *args, **kwargs):
        if self._publish:
            self._publish(*args, **kwargs)
        else:
            self.log.debug("Call to publish with no publish function set!")

    def _start_service(self, uid, service, args):
        self.log.debug('_start_service called for uid {uid}', uid=uid)
        existing = self.running_events_per_service[service]

        found_existing = False

        for _, existing_args in existing:
            if args == existing_args:
                found_existing = True
                break

        if found_existing:
            self.log.info("Maintaining already-running service {service} for UID {uid}", service=service, uid=uid)
            servicemanager.ensure_service(service, args)
        elif len(existing) > 0:
            self.log.error("Needing to start service {service}, which is already running with different arguments. Holding out until existing service is terminated.", service=service)
            return False
        else:
            self.log.info("Starting service {service} with args {args} (event UID: {uid}", service=service, args=args, uid=uid)
            servicemanager.start_service(service, args)

        self.runningEvents.append(uid)
        self.running_events_per_service[service].append([uid, args])

    def _stop_service(self, uid, service):
        existing = self.running_events_per_service[service]

        others = [e for e in existing if e[0] != uid]

        if len(others) == 0:
            self.log.info("Stopping service {}".format(service))
            servicemanager.stop_service(service)
        else:
            self.log.info("Maintaining already-running service {service} as other events are running", service=service)

        if uid in self.runningEvents:
            self.runningEvents.remove(uid)
        self.events.pop(uid)
        self.running_events_per_service[service] = others


def main():
    load_env()
    Logger().info("Starting scheduler service...")
    scheduler = Scheduler()
    scheduler.start()


if __name__ == '__main__':
    main()
