import contextlib
import functools
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

    def __init__(self):
        self._stdout_socket_writer = SocketWriter(prefix=b"1")
        self._stdout = io.TextIOWrapper(
            cast(BinaryIO, self._stdout_socket_writer), write_through=True
        )
        self._stderr_socket_writer = SocketWriter(prefix=b"2")
        self._stderr = io.TextIOWrapper(
            cast(BinaryIO, self._stderr_socket_writer), write_through=True
        )

        self._stdout_buffer = []
        self._stderr_buffer = []

    @contextlib.contextmanager
    def override_outputs_for_imports(self):
        prev_stdout = sys.stdout
        prev_stderr = sys.stderr

        self._override_output_stream_write(
            self._stdout, self._stdout_socket_writer, self._stdout_buffer
        )
        self._override_output_stream_write(
            self._stderr, self._stderr_socket_writer, self._stderr_buffer
        )
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        try:
            yield
        finally:
            sys.stdout = prev_stdout
            sys.stderr = prev_stderr
            del self._stdout.write
            del self._stderr.write

    @classmethod
    def _override_output_stream_write(cls, stream, socket_writer, buffer):
        orig_write = stream.write

        @functools.wraps(orig_write)
        def new_write(data: str):
            if not socket_writer.has_socket():
                buffer.append(data)
                return len(data)
            else:
                return orig_write(data)

        stream.write = new_write

    def set_socket(self, conn: socket.socket):
        self._stdout_socket_writer.set_socket(conn)
        for chunk in self._stdout_buffer:
            self._stdout.write(chunk)
        sys.stdout.flush()
        sys.stdout = self._stdout

        self._stderr_socket_writer.set_socket(conn)
        for chunk in self._stderr_buffer:
            self._stderr.write(chunk)
        sys.stderr.flush()
        sys.stderr = self._stderr


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
        return self._sock.fileno()

    def set_socket(self, sock: socket.socket):
        if self._sock is not None:
            raise Exception("SockerWriter socket may only be set once")
        self._sock = sock

    def has_socket(self) -> bool:
        return self._sock is not None
