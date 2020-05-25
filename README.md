# Timing 71: livetiming-core

[![License: AGPL v3](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![documentation](https://img.shields.io/badge/documentation-info.timing71.org-brightgreen)](https://info.timing71.org)
![Test status](https://github.com/timing71/livetiming-core/workflows/Tests/badge.svg)
![Latest release](https://img.shields.io/github/v/release/timing71/livetiming-core?sort=semver)

`livetiming-core` is the core functionality behind Timing 71's live timing
aggregator. It is a framework for obtaining, processing, analysing and
publishing motorsport live timing data feeds from a variety of sources.

It is modular and distributed by design, with a number of separate component
applications working together to enable functionality. It is based around WAMP,
and utilises Crossbar and Autobahn libraries to provide networking
functionality.

For documentation, and links to other open-source projects, visit
[info.timing71.org](https://info.timing71.org).

> ## Important IP notice
>
> This repository does **not** contain any code that directly obtains data from
> timing service providers. Due to their nature, those plugins often contain
> reverse-engineered proprietary or commercial code which it is therefore not
> possible to distribute in this repo.
>
> Even where the code is not reverse-engineered, to avoid any possible confusion
> with timing providers and rights holders, no plugins will be hosted in this
> repository.
>
> Pull requests that fall into this category will therefore not be accepted
> unless accompanied by permission from the timing data provider.
>
> Pull requests from timing data providers to include plugins for their services
> are very welcome!

## Purpose and function

Put simply, `livetiming-core` is a toolkit for:

- Extracting data from a timing provider
- Converting it to the Common Timing Data format
- Publishing that data to consumers over the Timing71 network (with
  authorisation), your own network, or locally to the desktop client
- Creating analysis data from that timing data

You achieve this by writing a _timing service plugin_, which is responsible for
extracting and converting the data.

Some additional commandline tools are also provided:

- **livetiming-analysis** can generate a JSON analysis data file from a
  recording ZIP file
- **livetiming-recordings** - manages the recordings catalogue from a
  directory on the local filesystem
- **livetiming-recordings-index** generates a recording catalogue JSON file
- **livetiming-service** runs a service instance

## Configuration

Configuration is largely through environment variables, which will also be read
from a `livetiming.env` file at startup if present.

### Global variables

- `LIVETIMING_ROUTER` - URL of the master router to connect to; if unspecified,
  services will start in standalone mode.
- `LIVETIMING_AUTH_ID` - Auth ID (username) for authenticating with the Timing71
  master router.
- `LIVETIMING_SHARED_SECRET` - a shared secret for authenticating with the
  master router. Only authenticated components may publish data or register RPC
  endpoints on the Timing71 network. Paired with the auth ID above.
- `SENTRY_DSN` - DSN to use for [Sentry](https://sentry.io/) error reporting
  service. If not set, then Sentry is not used.

### Service variables

- `LIVETIMING_ANALYSIS_DIR` - directory to store analysis data stores
- `LIVETIMING_STATE_DIR` - directory to store saved service state
- `LIVETIMING_LOG_DIR` - directory to store service logs

## Timing services

### Writing service plugins

All timing plugins should exist in the `livetiming.service.plugins` namespace
package, and implement the `livetiming.service.AbstractService` interface.
Rather than inherit from that class directly, most plugins will want to instead
inherit from `livetiming.service.BaseService` which provides some sensible
defaults as well as all the networking functionality.

To write your own plugin package, use the following directory layout (or
similar):

```text
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

Note the _lack_ of `__init__.py` files through most of the tree; that's
necessary to make Python's namespace packages work correctly.

Simple plugins may just require a `myplugin.py` in the `plugins/` directory.

In either case, your plugin **must** export a class `Service` that can be
referenced as e.g. `livetiming.service.plugins.myplugin.Service`.

An example of a very simple plugin is available in
[the `livetiming-plugin-example` repository](https://github.com/timing71/livetiming-plugin-example).

### Running manually

Service plugins can be run with:

```bash
livetiming-service <plugin_name> [<options>]
```

### Service options

Global service options include:

- `-d` or `--description`: override the description provided for the service
- `--debug`: enable debug-level logging
- `--disable-analysis`: Don't run analysis and live stats for this service
- `-H` or `--hidden`: Don't display this service on the website
- `--masquerade <service_class>`: Use specified `service_class` instead of the
  actual name of the class; can be used to disambiguate when multiple instances
  of the same class are running at once since the website will use service class
  by default in timing URLs
- `-r <filename>` or `--recording-filename <filename>`: produce a local
  recording file of this service (in addition to the DVR, if running)
- `-s <state_file>` or `--initial-state <state-file>`: bootstrap this service
  with an existing state file. You can use this to 'resume' a service that had
  previously been terminated.
- `-v` or `--verbose`: Log to stdout, not to a file (the latter is the
  default).

Most service plugins will define additional options.
