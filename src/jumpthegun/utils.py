import errno
import os


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
