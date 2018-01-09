# Live Timing Aggregator

The Live Timing Aggregator brings together timing feeds from multiple timing
service providers in a universal format for display and analysis.

It is modular and distributed by design, with a number of separate component
applications working together to enable functionality. It is based around
the web services application router Crossbar, and the Autobahn WAMP library.

## Components

The components involved in the LTA system are:

 - **Crossbar** - application router
 - **directory** - keeps a list of running timing services
 - **dvr** - records all running timing services and publishes completed
   recordings
 - **recordings directory** - lists details of recording files in a directory
 - **scheduler** - starts and stops timing services based on a schedule from
   Google Calendar
 - **timing services** - individual processes that retrieve timing data from a
   source, convert it to the universal format and broadcast it across the
   network
 - **web client** - the public-facing portion of the system, the website is
   where all the things are displayed

Some commandline tools are also provided:

 - **livetiming-rectool** inspects and manipulates recording files
 - **livetiming-service-manager** starts and stops services
 - **livetiming-service** runs a service instance

## Configuration

Configuration is largely through environment variables, read from the
`livetiming.env` file at startup.

### Global options

 - `LIVETIMING_ROUTER` - URL of the Crossbar router to connect to
 - `LIVETIMING_SHARED_SECRET` - a shared secret for authenticating internal
   components with the router. Only authenticated components may publish data
   or register RPC endpoints
 - `SENTRY_DSN` - DSN to use for Sentry error reporting service. If not set, then Sentry is not used

### Service options
 - `LIVETIMING_ANALYSIS_DIR` - directory to store analysis data stores
 - `LIVETIMING_STATE_DIR` - directory to store saved service state
 - `LIVETIMING_LOG_DIR` - directory to store service logs

### Scheduler options
 - `LIVETIMING_CALENDAR_URL` - URL of a Google calendar to use for service scheduling
 - `TWITTER_CONSUMER_KEY` - Twitter credentials used to tweet at start of
   services
 - `TWITTER_CONSUMER_SECRET`
 - `TWITTER_ACCESS_TOKEN`
 - `TWITTER_ACCESS_SECRET`

### Recording options
 - `LIVETIMING_RECORDINGS_DIR` - Directory to store completed, published recordings. This should also be web-accessible
 - `LIVETIMING_RECORDINGS_TEMP_DIR` - Directory to store in-progress recording
   files

### Web deployment options
 - `SENTRY_API_KEY` - API key used to upload source maps to Sentry

## Services

### Scheduling via Google Calendar

The easiest way to schedule services is via Google Calendar and the
`livetiming-scheduler` component. To mark an event as a service, it should have
certain parameters in [square brackets] folllowing the event title, defining
the service class and any options required.

For example:

```
My racing series - free practice 18 [awesome_race, --option foobar]
```
This defines an event called `My racing series - free practice 18` that will
use the `awesome_race` timing service, which will be run with the option
`--option foobar`.

### Running manually

Services can also be started and stopped with `livetiming-service-manager`:

```bash
livetiming-service-manager [start|stop|restart] <service_class> [<options>]
```

Or on their own:

```bash
livetiming-service <service_class> [<options>]
```

### Service options

Global service options include:
 - `-d` or `--description`: override the description provided for the service
 - `--debug`: enable debug-level logging
 - `--disable-analysis`: Don't run analysis and live stats for this service
 - `-H` or `--hidden`: Don't display this service on the website
 - `-r <filename>` or `--recording-filename <filename>`: produce a local 
   recording file of this service (in addition to the DVR, if running)
 - `-s <state_file>` or `--initial-state <state-file>`: bootstrap this service 
   with an existing state file. You can use this to 'resume' a service that had previously been terminated.
 - `-v` or `--verbose`: Log to stdout, not to a file (the latter is the 
   default).

Some service classes may define additional options.
