import argparse
import errno
import os
import signal
import sys

from subprocess32 import Popen


_PID_DIRECTORY = os.path.expanduser("~/.livetiming-service-pids/")


def _parse_args(raw_args):
    parser = argparse.ArgumentParser(description='Manager for live timing service processes.')

    parser.add_argument('action', choices=['start', 'stop'], help='Action: start or stop.')
    parser.add_argument('service_class', help='Class name of service to run')
    parser.add_argument('-s', '--initial-state', nargs='?', help='Initial state file')
    parser.add_argument('-r', '--recording-file', nargs='?', help='File to record timing data to')
    parser.add_argument('-d', '--description', nargs='?', help='Service description')
    parser.add_argument('-p', '--pid-directory', nargs='?', help='Directory to store pidfiles in', default=_PID_DIRECTORY)

    return parser.parse_args(raw_args)


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


def _start_service(args):
    if _pid_for(args.service_class, args.pid_directory) is not None:
        raise Exception("Service for {} already running!".format(args.service_class))
    else:
        extra_args = []
        if args.recording_file is not None:
            extra_args += ['-r', args.recording_file]
        if args.initial_state is not None:
            extra_args += ['-s', args.initial_state]
        if args.description is not None:
            extra_args += ['-d', args.description]
        p = Popen(['livetiming-service', args.service_class] + extra_args)
        _write_pid_for(args.service_class, p.pid, args.pid_directory)
        print "Started livetiming-service {} (PID {})".format(args.service_class, p.pid)


def _stop_service(args):
    pid = _pid_for(args.service_class, args.pid_directory)
    if pid is None:
        raise Exception("Service for {} not running!".format(args.service_class))
    else:
        try:
            os.kill(pid, signal.SIGINT)
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise e
        _clear_pid_for(args.service_class, args.pid_directory)
        print "Stopped livetiming-service {} (PID {})".format(args.service_class, pid)


def start_service(service_class, args):
    return _start_service(_parse_args(["start", service_class] + args))


def stop_service(service_class):
    return _start_service(_parse_args(["stop", service_class]))


def main():
    args = _parse_args(sys.argv[1:])
    if args.action == "start":
        _start_service(args)
    elif args.action == "stop":
        _stop_service(args)


if __name__ == '__main__':
    main()
