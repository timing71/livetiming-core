# Timing 71: livetiming-core

`livetiming-core` is the core functionality behind Timing 71's live timing
aggregator. It is a framework for obtaining, processing, analysing and
publishing motorsport live timing data feeds from a variety of sources.

It is modular and distributed by design, with a number of separate component
applications working together to enable functionality. It is based around WAMP,
and utilises Crossbar and Autobahn libraries to provide networking
functionality.

## Important IP notice

This repository does **not** contain code for any timing services themselves.
Due to their nature, they often contain reverse-engineered proprietary or
commercial code and so it is not possible to distribute those.

PRs for timing plugins that are written in such a way will _not_ be accepted
unless they are authored by, or granted permission by, the owner of the original
code. (If you're a commercial timing provider and want to contribute, you are
very welcome to!)

## Components

The components involved in the Aggregator are:

- **Timing services** - individual processes that retrieve timing data from a
  source, convert it to the universal format and broadcast it across the
  network via the master router
- **Master router** - Crossbar WAMP router
- **livetiming-directory** - keeps a list of running timing services
- **livetiming-dvr** - records all running timing services and publishes
  completed recordings to the configured recordings directory
- **livetiming-recordings** - manages the recordings catalogue from a
  directory on the local filesystem
- **livetiming-scheduler** - starts and stops timing services based on a
  schedule from Google Calendar

Some additional commandline tools are also provided:

- **livetiming-analysis** can generate a JSON analysis data file from a
  recording ZIP file
- **livetiming-recordings-index** generates a recording catalogue JSON file
- **livetiming-rectool** inspects and manipulates recording files
- **livetiming-schedule** can both check and generate (via `assist`) a GCal-
  based schedule
- **livetiming-service-manager** starts and stops services
- **livetiming-service** runs a service instance

## Configuration

Configuration is largely through environment variables, which will also be read
from a `livetiming.env` file at startup if present.

### Global variables

- `LIVETIMING_ROUTER` - URL of the Crossbar router to connect to
- `LIVETIMING_SHARED_SECRET` - a shared secret for authenticating internal
  components with the router. Only authenticated components may publish data
  or register RPC endpoints
- `SENTRY_DSN` - DSN to use for Sentry error reporting service. If not set, then    Sentry is not used

### Service variables

- `LIVETIMING_ANALYSIS_DIR` - directory to store analysis data stores
- `LIVETIMING_STATE_DIR` - directory to store saved service state
- `LIVETIMING_LOG_DIR` - directory to store service logs

### Scheduler variables

- `LIVETIMING_CALENDAR_URL` - URL of a Google calendar to use for service scheduling
- `TWITTER_CONSUMER_KEY` - Twitter credentials used to tweet at start of
  services
- `TWITTER_CONSUMER_SECRET`
- `TWITTER_ACCESS_TOKEN`
- `TWITTER_ACCESS_SECRET`

### Recording variables

- `LIVETIMING_RECORDINGS_DIR` - Directory to store completed, published recordings. This should also be web-accessible
- `LIVETIMING_RECORDINGS_TEMP_DIR` - Directory to store in-progress recording
  files

## Timing services

### Writing service plugins

All timing plugins should exist in the `livetiming.service.plugins` namespace
package, and implement the `livetiming.service.AbstractService` interface.
Rather than inherit from that class directly, most plugins will want to instead
inherit from `livetiming.service.BaseService` which provides some sensible
defaults as well as all the networking functionality.

To write your own plugin package, use the following directory layout (or
similar):

```
src/
|- livetiming/
    |- service/
        |- plugins/
            |- myplugin/
                |- __init__.py
                |- (...other files as needed)
setup.py
(etc)
```

Note the _lack_ of `__init__.py` files through most of the tree; that's necessary to make Python's namespace packages work correctly.

Simple plugins may just require a `myplugin.py` in the `plugins/` directory.

In either case, your plugin **must** export a class `Service` that can be
referenced as `livetiming.service.plugins.myplugin.Service`.

### Running manually

Services can be started and stopped with `livetiming-service-manager`:

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

Most service plugins will define additional options.

### Scheduling via Google Calendar

The easiest way to schedule services is via Google Calendar and the
`livetiming-scheduler` component. To mark an event as a service, it should have
certain parameters in [square brackets] folllowing the event title, defining
the service class and any options required.

For example:

`My racing series - free practice 18 [awesome_race, --option foobar]`

This defines an event called `My racing series - free practice 18` that will
use the `awesome_race` timing service, which will be run with the option
`--option foobar`.
