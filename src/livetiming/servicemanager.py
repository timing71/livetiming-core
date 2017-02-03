import argparse
import errno
import os
import signal
import sys

from subprocess32 import Popen


_PID_DIRECTORY = os.path.expanduser("~/.livetiming-service-pids/")


class ServiceManagementException(Exception):
    pass


def _parse_args(raw_args):
    parser = argparse.ArgumentParser(description='Manager for live timing service processes.')

    parser.add_argument('action', choices=['start', 'stop', 'restart'], help='Action: start or stop.')
    parser.add_argument('service_class', help='Class name of service to run')
    parser.add_argument('-p', '--pid-directory', nargs='?', help='Directory to store pidfiles in', default=_PID_DIRECTORY)

    return parser.parse_known_args(raw_args)


def _pid_for(service_class, pid_directory):
    pidfile = os.path.join(pid_directory, service_class)
    try:
        with open(pidfile, 'r') as f:
            return int(f.read())
    except:
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


def _start_service(args, extras):
    if _pid_for(args.service_class, args.pid_directory) is not None:
        raise ServiceManagementException("Service for {} already running!".format(args.service_class))
    else:
        p = Popen(['livetiming-service', args.service_class] + extras)
        _write_pid_for(args.service_class, p.pid, args.pid_directory)
        print "Started livetiming-service {} (PID {})".format(args.service_class, p.pid)


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
        print "Stopped livetiming-service {} (PID {})".format(args.service_class, pid)


def start_service(service_class, args):
    return _start_service(*_parse_args(["start", service_class] + args))


def stop_service(service_class):
    return _stop_service(_parse_args(["stop", service_class])[0])


def main():
    args, extras = _parse_args(sys.argv[1:])
    if args.action == "start":
        _start_service(args, extras)
    elif args.action == "stop":
        _stop_service(args)
    elif args.action == "restart":
        try:
            _stop_service(args)
        except ServiceManagementException:
            pass
        _start_service(args)


if __name__ == '__main__':
    main()
