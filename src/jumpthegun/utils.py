import errno
import os
import sys


def pid_exists(pid: int):
    """Check whether a process with the given pid exists."""
    if not (isinstance(pid, int) and pid > 0):
        raise ValueError(f"Invalid PID: {pid}")

    try:
        os.kill(pid, 0)
    except OSError as err:
        if err.errno == errno.ESRCH:
            # No such process.
            return False
        elif err.errno == errno.EPERM:
            # Permission denied - such a process must exist.
            return True
        else:
            raise
    else:
        return True


def daemonize():
    """Do the double-fork dance to daemonize."""
    # See:
    # * https://stackoverflow.com/a/5386753
    # * https://www.win.tue.nl/~aeb/linux/lk/lk-10.html
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    # redirect standard file descriptors
    sys.__stdout__.flush()
    sys.__stderr__.flush()
    stdin = open("/dev/null", "rb")
    stdout = open("/dev/null", "ab")
    stderr = open("/dev/null", "ab")
    os.dup2(stdin.fileno(), sys.__stdin__.fileno())
    os.dup2(stdout.fileno(), sys.__stdout__.fileno())
    os.dup2(stderr.fileno(), sys.__stderr__.fileno())
