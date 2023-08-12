import hashlib
import os
import random
import shlex
import string
import subprocess
import tempfile
from pathlib import Path

from jumpthegun._vendor.filelock import FileLock


def get_jumpthegun_runtime_dir() -> Path:
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


def get_isolated_service_runtime_dir_for_tool(tool_name: str) -> Path:
    tool_executable_path: bytes = subprocess.run(
        f"command -v {shlex.quote(tool_name)}",
        shell=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    return get_isolated_service_runtime_dir_for_executable(tool_executable_path)


def get_isolated_service_runtime_dir_for_executable(executable_path: bytes) -> Path:
    executable_dir = os.path.dirname(executable_path)
    isolation_hash: str = hashlib.sha256(executable_dir).hexdigest()[:8]
    isolated_path: Path = get_jumpthegun_runtime_dir() / isolation_hash

    isolated_path.mkdir(exist_ok=True, mode=0o700)
    return isolated_path
