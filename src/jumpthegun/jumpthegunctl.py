import io
import os
import shlex
import signal
import socket
import sys
import time
import traceback
from pathlib import Path
from typing import BinaryIO, Dict, Tuple, cast

from .__version__ import __version__
from .config import read_config
from .env_vars import apply_env_with_diff, calc_env_diff
from .io_redirect import SocketOutputRedirector, StdinWrapper
from .runtime_dir import get_isolated_service_runtime_dir_for_tool
from .tools import ToolExceptionBase, get_tool_entrypoint
from .utils import daemonize as daemonize_func
from .utils import pid_exists


class InvalidCommand(Exception):
    def __init__(self, command: str):
        super().__init__(command)
        self.command = command


class DaemonAlreadyExistsError(ToolExceptionBase):
    def __str__(self):
        return (
            f'Jump the Gun daemon process for tool "{self.tool_name}" already exists.'
        )


class DaemonDoesNotExistError(ToolExceptionBase):
    def __str__(self):
        return (
            f'Jump the Gun daemon process for tool "{self.tool_name}" does not exist.'
        )


def get_pid_and_port_file_paths(tool_name: str) -> Tuple[Path, Path]:
    service_runtime_dir_path = get_isolated_service_runtime_dir_for_tool(tool_name)
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
    config = read_config()

    # Import the tool and get its entrypoint function.
    #
    # Override sys.stdout and sys.stderr while loading the tool runner,
    # so that any references to them kept during module imports (e.g for
    # setting up logging) already reference the overrides.
    output_redirector = SocketOutputRedirector()
    with output_redirector.override_outputs_for_imports():
        tool_entrypoint = get_tool_entrypoint(tool_name)
        env_before = dict(os.environ)
        tool_runner = tool_entrypoint.load()
        env_after = dict(os.environ)
        env_diff = calc_env_diff(env_before, env_after)

    pid_file_path, port_file_path = get_pid_and_port_file_paths(tool_name)

    if pid_file_path.exists():
        file_pid = int(pid_file_path.read_text())
        if pid_exists(file_pid):
            raise DaemonAlreadyExistsError(tool_name=tool_name)

    if daemonize:
        print(f'"jumpthegun {tool_name}" daemon process starting...')
        daemonize_func()

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
    sock.settimeout(config.idle_timeout_seconds)
    subproc_pids: set[int] = set()
    try:
        while True:
            conn, address = sock.accept()
            print(f"Got connection from: {address}")
            newpid = os.fork()
            if newpid == 0:
                break

            # Avoid "zombie" processes: Reap completed sub-processes.
            done_subproc_pids = {
                x for x in subproc_pids if os.waitpid(x, os.WNOHANG)[0] != 0
            }
            subproc_pids -= done_subproc_pids
            subproc_pids.add(newpid)
    except BaseException as exc:
        # Server is exiting: Clean up as needed.
        sock.close()
        if pid_file_path.exists():
            file_pid = int(pid_file_path.read_text())
            if file_pid == pid:
                pid_file_path.unlink(missing_ok=True)
                port_file_path.unlink(missing_ok=True)
        if isinstance(exc, socket.timeout):
            print(
                f"Exiting after receiving no connections for {config.idle_timeout_seconds} seconds."
            )
            return
        raise

    # Send pid.
    conn.sendall(b"%d\n" % os.getpid())

    rfile = conn.makefile("rb", 0)

    # Read and set argv
    argv_bytes = rfile.read(int(rfile.readline()))
    sys.argv[1:] = shlex.split(argv_bytes.decode()) if argv_bytes else []
    sys.argv[0] = tool_name

    # Read and set cwd
    pwd = rfile.read(int(rfile.readline()))
    if not pwd:
        raise Exception("Did not receive pwd from client.")
    os.chdir(pwd)

    # Read and set env vars
    env_vars_str: str = (rfile.read(int(rfile.readline())) or b"").decode()
    split_lines = (line.split("=", 1) for line in env_vars_str.split("\0"))
    env: Dict[str, str] = dict(line for line in split_lines if len(line) == 2)
    env.pop("_", None)
    apply_env_with_diff(env, env_diff)

    sys.stdin.close()
    sys.stdin = io.TextIOWrapper(cast(BinaryIO, StdinWrapper(conn)))
    output_redirector.set_socket(conn)

    # start_time = time.monotonic()
    exit_code: int
    try:
        retval = tool_runner()
    except BaseException as exc:
        # end_time = time.monotonic()
        # print(f"Time: {end_time - start_time}", file=sys.__stdout__)
        # print("EXCEPTION", str(exc), file=sys.__stderr__)
        if isinstance(exc, SystemExit):
            exit_code = exc.code if isinstance(exc.code, int) else 1
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
        get_tool_entrypoint(tool_name)
    except ToolExceptionBase:
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
