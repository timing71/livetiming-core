import argparse
import errno
import os
import re
import signal
import sys

from livetiming import load_env
from subprocess32 import Popen


_PID_DIRECTORY = os.environ.get("LIVETIMING_PID_DIR", os.path.expanduser("~/.livetiming-service-pids/"))


class ServiceManagementException(Exception):
    pass


def _parse_args(raw_args):
    parser = argparse.ArgumentParser(description='Manager for live timing service processes.')

    parser.add_argument('action', choices=['start', 'stop', 'restart'], help='Action: start or stop.')
    parser.add_argument('service_class', help='Class name of service to run')
    parser.add_argument('-p', '--pid-directory', nargs='?', help='Directory to store pidfiles in', default=_PID_DIRECTORY)
    parser.add_argument('-f', '--fresh', action='store_true', help='Don\'t attempt to restore state')

    return parser.parse_known_args(raw_args)


def _pid_for(service_class, pid_directory):
    pidfile = os.path.join(pid_directory, service_class)
    try:
        with open(pidfile, 'r') as f:
            return int(f.read())
    except IOError:
        return None


def _write_pid_for(service_class, pid, pid_directory):
    if not os.path.isdir(pid_directory):
        os.mkdir(pid_directory)
    pidfile = os.path.join(pid_directory, service_class)
    with open(pidfile, 'w') as f:
        f.write("{}".format(pid))
        f.flush()


def _clear_pid_for(service_class, pid_directory):
    pidfile = os.path.join(pid_directory, service_class)
    os.remove(pidfile)


def _process_exists(pid):
    pids = [int(x) for x in os.listdir("/proc") if x.isdigit()]
    return pid in pids


def _read_uuid_for(service_class):
    logfile = os.path.join(
        os.environ.get("LIVETIMING_LOG_DIR", os.getcwd()),
        "{}.log".format(service_class)
    )
    if os.path.exists(logfile):
        with open(logfile, 'r') as log:
            most_recent_pid = None
            PID_REGEX = re.compile(r"[0-9T\-+:]+ Session ready for service (?P<pid>[0-9a-z]{32})")
            for line in log:
                m = PID_REGEX.match(line)
                if m:
                    most_recent_pid = m.group("pid")
            return most_recent_pid
    return None


def _start_service(args, extras):
    existing_pid = _pid_for(args.service_class, args.pid_directory)
    if existing_pid is not None:
        if _process_exists(existing_pid):
            raise ServiceManagementException("Service for {} already running!".format(args.service_class))
        print("Ignoring stale PID {}".format(existing_pid))
    p = Popen(['livetiming-service', args.service_class] + extras)
    _write_pid_for(args.service_class, p.pid, args.pid_directory)
    print("Started livetiming-service {} (PID {})".format(args.service_class, p.pid))
    return p.pid


def _stop_service(args):
    pid = _pid_for(args.service_class, args.pid_directory)
    if pid is None:
        raise ServiceManagementException("Service for {} not running!".format(args.service_class))
    else:
        try:
            os.kill(pid, signal.SIGINT)
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise e
        _clear_pid_for(args.service_class, args.pid_directory)
        print("Stopped livetiming-service {} (PID {})".format(args.service_class, pid))


def _restart_service(args, extras):
    if not args.fresh:
        uuid = _read_uuid_for(args.service_class)
        if uuid:
            statefile = os.path.join(
                os.environ.get("LIVETIMING_STATE_DIR", os.getcwd()),
                "{}.json".format(uuid)
            )
            if os.path.exists(statefile):
                print("Reusing existing state for {}: {}".format(uuid, statefile))
                extras += ["-s", statefile]
    try:
        _stop_service(args)
    except ServiceManagementException:
        pass
    return _start_service(args, extras)


def start_service(service_class, args):
    return _start_service(*_parse_args(["start", service_class] + args))


def ensure_service(service_class, args):
    '''
      This method behaves like `start_service` but throws no exceptions if a service
      is already running. Thus, it can be used to ensure that the given service is
      running, and start one with the given args if not.

      It makes no attempt to verify that the running service was started with the same
      arguments as passed to this function.
    '''
    try:
        return _start_service(*_parse_args(["start", service_class] + args))
    except ServiceManagementException:
        return False


def stop_service(service_class):
    return _stop_service(_parse_args(["stop", service_class])[0])


def main():
    load_env()
    args, extras = _parse_args(sys.argv[1:])
    if args.action == "start":
        _start_service(args, extras)
    elif args.action == "stop":
        _stop_service(args)
    elif args.action == "restart":
        _restart_service(args, extras)


if __name__ == '__main__':
    main()
