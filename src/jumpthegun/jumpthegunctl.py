import hashlib
import io
import os
import random
import shlex
import signal
import socket
import string
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, BinaryIO, Optional, Set, Tuple, Union, cast

from jumpthegun.project import get_tool_names
from vendor.filelock import FileLock

from .__version__ import __version__
from .tools import ToolExceptionBase, UnsupportedTool, get_tool_runner
from .utils import pid_exists


class InvalidCommand(Exception):
    def __init__(self, command: str):
        super().__init__(command)
        self.command = command


class DaemonAlreadyExistsError(ToolExceptionBase):
    def __str__(self):
        return f'Jump the Gun daemon process for tool "{self.tool_name}" already exists.'


class DaemonDoesNotExistError(ToolExceptionBase):
    def __str__(self):
        return f'Jump the Gun daemon process for tool "{self.tool_name}" does not exist.'


class _SocketWriter(io.RawIOBase):
    """TODO!"""

    def __init__(self, sock: socket.socket, prefix: Union[bytes, bytearray]) -> None:
        self._sock = sock
        self._prefix = prefix

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def write(self, b: Union[bytes, bytearray]) -> int:  # type: ignore[override]
        n_newlines = b.count(10)
        # print(b"%b%d\n%b\n" % (self._prefix, n_newlines, b), file=sys.__stderr__)
        self._sock.sendall(b"%b%d\n%b\n" % (self._prefix, n_newlines, b))
        # print("DONE WRITING", file=sys.__stderr__)
        with memoryview(b) as view:
            return view.nbytes

    def fileno(self) -> Any:
        return self._sock.fileno()


class StdinWrapper(io.RawIOBase):
    """TODO!"""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def readline(self, size: Optional[int] = -1) -> bytes:
        # print(f"readline({size=})", file=sys.__stdout__)
        if size is None:
            size = -1
        self._sock.sendall(b"3\n")
        buf = self._buf
        while size:
            chunk = self._sock.recv(size if size != -1 else 4096)
            # print(f"CHUNK {chunk}", file=sys.__stdout__)
            if not chunk:
                self._buf = bytearray()
                break
            idx = chunk.find(10)  # ord("\n") == 10
            if idx >= 0:
                size = idx + 1
            if len(chunk) >= size:
                buf.extend(chunk[:size])
                self._buf = bytearray(chunk[size:])
                break
            buf.extend(chunk)
            size = size - len(chunk) if size != -1 else -1

        return buf

    read = readline

    def fileno(self) -> Any:
        return self._sock.fileno()


def get_service_runtime_dir_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        service_runtime_dir = Path(runtime_dir) / "jumpthegun"
        service_runtime_dir.mkdir(exist_ok=True, mode=0o700)
        return service_runtime_dir

    temp_dir_path = Path(tempfile.gettempdir())
    service_runtime_dirs = list(
        temp_dir_path.glob(f"jumpthegun-{os.getenv('USER')}-??????")
    )
    if service_runtime_dirs:
        if len(service_runtime_dirs) > 1:
            raise Exception("Error: Multiple service runtime dirs found.")
        return service_runtime_dirs[0]

    lock = FileLock(temp_dir_path / f"jumpthegun-{os.getenv('USER')}.lock")
    with lock:
        service_runtime_dirs = list(
            temp_dir_path.glob(f"jumpthegun-{os.getenv('USER')}-??????")
        )
        if service_runtime_dirs:
            return service_runtime_dirs[0]

        random_part = "".join([random.choice(string.ascii_letters) for _i in range(6)])
        service_runtime_dir = (
            temp_dir_path / f"jumpthegun-{os.getenv('USER')}-{random_part}"
        )
        service_runtime_dir.mkdir(exist_ok=False, mode=0o700)
        return service_runtime_dir


def get_isolated_service_runtime_dir_path(tool_name) -> Path:
    service_runtime_dir = get_service_runtime_dir_path()

    tool_executable_path: bytes = subprocess.run(
        f"command -v {shlex.quote(tool_name)}",
        shell=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    tool_executable_dir_path: bytes = os.path.dirname(tool_executable_path)
    isolation_hash: str = hashlib.sha256(tool_executable_dir_path).hexdigest()[:8]
    isolated_path: Path = service_runtime_dir / isolation_hash

    isolated_path.mkdir(exist_ok=True, mode=0o700)
    return isolated_path


def get_pid_and_port_file_paths(tool_name: str) -> Tuple[Path, Path]:
    service_runtime_dir_path = get_isolated_service_runtime_dir_path(tool_name)
    pid_file_path = service_runtime_dir_path / f"{tool_name}.pid"
    port_file_path = service_runtime_dir_path / f"{tool_name}.port"
    return pid_file_path, port_file_path


def remove_pid_and_port_files(tool_name: str) -> None:
    for file_path in get_pid_and_port_file_paths(tool_name):
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass


def daemon_teardown(
    sock: socket.socket, pid: int, pid_file_path: Path, port_file_path: Path
) -> None:
    """Close socket and remove pid and port files upon daemon shutdown."""
    sock.close()
    if pid_file_path.exists():
        file_pid = int(pid_file_path.read_text())
        if file_pid == pid:
            pid_file_path.unlink(missing_ok=True)
            port_file_path.unlink(missing_ok=True)


def start(tool_name: str, daemonize: bool = True) -> None:
    tool_runner = get_tool_runner(tool_name)

    pid_file_path, port_file_path = get_pid_and_port_file_paths(tool_name)

    if pid_file_path.exists():
        file_pid = int(pid_file_path.read_text())
        if pid_exists(file_pid):
            raise DaemonAlreadyExistsError(tool_name=tool_name)

    if daemonize:
        # Do the double-fork dance to daemonize.
        # See:
        # * https://stackoverflow.com/a/5386753
        # * https://www.win.tue.nl/~aeb/linux/lk/lk-10.html

        pid = os.fork()
        if pid > 0:
            print(f'"jumpthegun {tool_name}" daemon process starting...')
            return

        os.setsid()

        pid = os.fork()
        if pid > 0:
            sys.exit(0)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        stdin = open("/dev/null", "rb")
        stdout = open("/dev/null", "ab")
        stderr = open("/dev/null", "ab")
        os.dup2(stdin.fileno(), sys.stdin.fileno())
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        os.dup2(stderr.fileno(), sys.stderr.fileno())

    # Write pid file.
    pid = os.getpid()
    pid_file_path.write_bytes(b"%d\n" % pid)

    # Open socket.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))

    # Write port file.
    host, port = sock.getsockname()
    port_file_path.write_bytes(b"%d\n" % port)

    # Listen for connections.
    sock.listen()
    print(f"Listening on {host}:{port} (pid={pid}) ...")
    subproc_pids = set()
    try:
        while True:
            conn, address = sock.accept()
            print(f"Got connection from: {address}")
            newpid = os.fork()
            if newpid == 0:
                break

            # Avoid "zombie" processes: Reap completed sub-processes.
            done_subproc_pids = {x for x in subproc_pids if os.waitpid(x, os.WNOHANG)[0] != 0}
            subproc_pids -= done_subproc_pids
            subproc_pids.add(newpid)
    except BaseException:
        # Server is exiting: Clean up as needed.
        sock.close()
        if pid_file_path.exists():
            file_pid = int(pid_file_path.read_text())
            if file_pid == pid:
                pid_file_path.unlink(missing_ok=True)
                port_file_path.unlink(missing_ok=True)
        raise

    # Send pid.
    conn.sendall(b"%d\n" % os.getpid())

    rfile = conn.makefile("rb", 0)
    sys.argv[1:] = shlex.split(rfile.readline().strip().decode())
    sys.argv[0] = tool_name

    sys.stdin.close()
    sys.stdin = io.TextIOWrapper(cast(BinaryIO, StdinWrapper(conn)))
    sys.stdout = io.TextIOWrapper(
        cast(BinaryIO, _SocketWriter(conn, b"1")), write_through=True
    )
    sys.stderr = io.TextIOWrapper(
        cast(BinaryIO, _SocketWriter(conn, b"2")), write_through=True
    )

    # start_time = time.monotonic()
    try:
        retval = tool_runner()
    except BaseException as exc:
        # end_time = time.monotonic()
        # print(f"Time: {end_time - start_time}", file=sys.__stdout__)
        # print("EXCEPTION", str(exc), file=sys.__stderr__)
        if isinstance(exc, SystemExit):
            exit_code = exc.code
        else:
            traceback.print_exc()
            exit_code = 1
        # print(f"{exit_code=}", file=sys.__stdout__)
        if isinstance(exit_code, bool):
            exit_code = int(exit_code)
        elif not isinstance(exit_code, int):
            exit_code = 1
    else:
        if isinstance(retval, int):
            exit_code = retval
        else:
            exit_code = 0
    finally:
        conn.sendall(b"rc=%d\n" % exit_code)
        # print(f"Goodbye! rc={exit_code}", file=sys.__stdout__)

        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()
        conn.shutdown(socket.SHUT_WR)
        sys.exit(0)


def stop(tool_name: str) -> None:
    try:
        get_tool_runner(tool_name)
    except UnsupportedTool:
        raise DaemonDoesNotExistError(tool_name)

    try:
        pid_file_path, _port_file_path = get_pid_and_port_file_paths(tool_name)
        if not pid_file_path.exists():
            raise DaemonDoesNotExistError(tool_name)

        file_pid = int(pid_file_path.read_text())
        if not pid_exists(file_pid):
            raise DaemonDoesNotExistError(tool_name)

        os.kill(file_pid, signal.SIGTERM)
        for _i in range(20):
            time.sleep(0.05)
            if not pid_exists(file_pid):
                break
        else:
            os.kill(file_pid, signal.SIGKILL)

        print(f'"jumpthegun {tool_name}" daemon process stopped.')

    finally:
        remove_pid_and_port_files(tool_name)


def print_usage() -> None:
    """Print a message about how to run jumpthegunctl."""
    print(f"Usage: {sys.argv[0]} start|stop tool_name")


def do_action(tool_name: str, action: str) -> None:
    """Apply an action (e.g. start or stop) for a given tool."""
    if action == "start":
        start(tool_name)
    elif action == "stop":
        stop(tool_name)
    elif action == "restart":
        try:
            stop(tool_name)
        except DaemonDoesNotExistError:
            pass
        start(tool_name)
    else:
        raise InvalidCommand(action)


def main() -> None:
    args = sys.argv[1:]

    if any(arg == "-h" or arg == "--help" for arg in args):
        print_usage()
        sys.exit(0)

    if len(args) == 1:
        (cmd,) = args
        if cmd == "version" or cmd == "--version":
            print(f"jumpthegun v{__version__}")
            sys.exit(0)
    elif len(args) == 2:
        (cmd, tool_name) = args
        tool_name = tool_name.strip().lower()

        if tool_name == "all":
            tool_names = get_tool_names(Path.cwd())
            failed_for_tools: Set[str] = set()
            for _tool_name in tool_names:
                try:
                    do_action(tool_name=_tool_name, action=cmd)
                except ToolExceptionBase:
                    failed_for_tools.add(_tool_name)

            succeeded_for_tools = set(tool_names) - failed_for_tools
            if cmd == "restart":
                if succeeded_for_tools:
                    print(
                        "Restarted jumpthegun daemons for tools:",
                        ", ".join(sorted(succeeded_for_tools)),
                    )
                    sys.exit(0)
                if failed_for_tools:
                    print(
                        "Failed to restart jumpthegun daemons for tools:",
                        ", ".join(sorted(failed_for_tools)),
                    )
                    sys.exit(1)
            elif cmd == "start" or cmd == "stop":
                if succeeded_for_tools:
                    action_str = "Stopped" if cmd == "stop" else "Started"
                    print(
                        f"{action_str} jumpthegun daemons for tools:",
                        ", ".join(sorted(succeeded_for_tools)),
                    )
                    sys.exit(0)
                else:
                    print(f"No tools to {cmd} jumpthegun daemons for.")
                    sys.exit(0)
        else:
            try:
                do_action(tool_name=tool_name, action=cmd)
            except ToolExceptionBase as exc:
                print(str(exc))
                sys.exit(1)
            except InvalidCommand as exc:
                print(str(exc))
            else:
                sys.exit(0)

    print_usage()
    sys.exit(1)


if __name__ == "__main__":
    main()
