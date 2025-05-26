import contextlib
import io
import socket
import sys
from typing import Any, BinaryIO, Optional, Union, cast


class SocketOutputRedirector:
    """Helper class for redirecting stdout and stderr.

    This redirects to a socket, writing in the JumpTheGun protocol.

    Use the .override_outputs_for_imports() context manager to
    temporarily override stdout and stderr, buffering all data written
    to them.

    Later, use .set_socket() to set the socket to be written to and
    override stdout and stderr in a final manner.  At this point, any
    buffered data will be written to the socket.
    """

    _stdout_buffer: io.StringIO
    _stderr_buffer: io.StringIO

    def __init__(self):
        self._stdout_buffer = io.StringIO()
        self._stderr_buffer = io.StringIO()

    @contextlib.contextmanager
    def override_outputs_for_imports(self):
        prev_stdout = sys.stdout
        prev_stderr = sys.stderr

        sys.stdout = self._stdout_buffer
        sys.stderr = self._stderr_buffer
        try:
            yield
        finally:
            sys.stdout = prev_stdout
            sys.stderr = prev_stderr

    def set_socket(self, conn: socket.socket):
        stdout_socket_writer = SocketWriter(prefix=b"1")
        stdout_socket_writer.set_socket(conn)
        sock_stdout = io.TextIOWrapper(
            cast(BinaryIO, stdout_socket_writer), write_through=True
        )
        sock_stdout.write(self._stdout_buffer.getvalue())
        sys.stdout.flush()
        sys.stdout = sock_stdout

        stderr_socket_writer = SocketWriter(prefix=b"2")
        stderr_socket_writer.set_socket(conn)
        sock_stderr = io.TextIOWrapper(
            cast(BinaryIO, stderr_socket_writer), write_through=True
        )
        sock_stderr.write(self._stderr_buffer.getvalue())
        sys.stderr.flush()
        sys.stderr = sock_stderr


class SocketWriter(io.RawIOBase):
    """Output adapter implementing the file interface.

    This writes lines to a socket in the JumpTheGun protocol.

    The socket is set after initialization via .set_socket().
    """

    _sock: Optional[socket.socket]

    def __init__(self, prefix: bytes) -> None:
        self._sock = None
        self._prefix = prefix

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def write(self, b: Union[bytes, bytearray]) -> int:  # type: ignore[override]
        if self._sock is None:
            raise Exception("SocketWriter socket must be set before calling .write()")
        n_newlines = b.count(10)
        # print(b"%b%d\n%b\n" % (self._prefix, n_newlines, b), file=sys.__stderr__)
        self._sock.sendall(b"%b%d\n%b\n" % (self._prefix, n_newlines, b))
        # print("DONE WRITING", file=sys.__stderr__)
        with memoryview(b) as view:
            return view.nbytes

    def fileno(self) -> Any:
        return self._sock.fileno() if self._sock is not None else None

    def set_socket(self, sock: socket.socket):
        if self._sock is not None:
            raise Exception("SockerWriter socket may only be set once")
        self._sock = sock

    def has_socket(self) -> bool:
        return self._sock is not None


class StdinWrapper(io.RawIOBase):
    """Input adapter implementing the file interface.

    This reads lines from a socket in the JumpTheGun protocol.
    """

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = bytearray()

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def readline(self, size: Optional[int] = -1) -> bytes:
        if size is None:
            size = -1
        self._sock.sendall(b"3\n")
        buf = self._buf
        while size:
            chunk = self._sock.recv(size if size != -1 else 4096)
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
