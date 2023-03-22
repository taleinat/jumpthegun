import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest


def get_bin_path(project_path: Path) -> Path:
    return (
        project_path.parent / "venv" / ("Scripts" if sys.platform == "win32" else "bin")
    )


# @pytest.fixture(scope="session")
# def setup_testproj() -> Path:
#     with tempfile.TemporaryDirectory() as tmp_dir:
#         proj_dir = Path(tmp_dir) / "testproj"
#         shutil.copytree(Path(__file__).parent / "testproj", proj_dir)
#         venv_path = proj_dir / "venv"
#         subprocess.run([sys.executable, "-mvenv", str(venv_path)])
#         bin_path = get_bin_path(proj_dir)
#         subprocess.run([str(bin_path / "pip"), "install", ".", "black", "flake8", "isort"], cwd=str(Path(__file__).parents[1]), check=True)
#         yield proj_dir
#
#
# @pytest.fixture
# def testproj(setup_testproj, tmp_path) -> Path:
#     proj_dir = Path(tmp_path) / "testproj"
#     shutil.copytree(setup_testproj, proj_dir)
#     yield proj_dir


@pytest.fixture(scope="session")
def testproj() -> Path:
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_dir = Path(tmp_dir) / "testproj"
        sources_dir = Path(__file__).parent / "testproj"
        shutil.copytree(sources_dir, proj_dir)
        venv_path = Path(tmp_dir) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        bin_path = get_bin_path(proj_dir)
        subprocess.run(
            [str(bin_path / "pip"), "install", ".", "black", "flake8", "isort"],
            cwd=str(Path(__file__).parents[1]),
            check=True,
        )
        sleep_and_exit_on_signal_script = textwrap.dedent("""\
            #!/usr/bin/env python
            import jumpthegun.testutils
            
            jumpthegun.testutils.sleep_and_exit_on_signal()
            """)
        (bin_path / "__test_sleep_and_exit_on_signal").write_text(sleep_and_exit_on_signal_script)
        yield proj_dir


@pytest.mark.parametrize(
    "tool_cmd",
    [
        ["black", "--check", "."],
        ["isort", "--check", "."],
        ["flake8"],
    ],
    ids=lambda tool_cmd: tool_cmd[0],
)
def test_jumpthegun_start_run_stop(testproj, tool_cmd):
    without_jumpthegun_proc = run(tool_cmd, proj_path=testproj)
    assert without_jumpthegun_proc.returncode != 0
    run(["jumpthegun", "start", tool_cmd[0]], proj_path=testproj, check=True)
    try:
        with_jumpthegun_proc = run(["jumpthegun", "run", *tool_cmd], proj_path=testproj)
    finally:
        run(["jumpthegun", "stop", tool_cmd[0]], proj_path=testproj, check=True)

    assert with_jumpthegun_proc.stdout == without_jumpthegun_proc.stdout
    assert with_jumpthegun_proc.stderr == without_jumpthegun_proc.stderr
    assert with_jumpthegun_proc.returncode == without_jumpthegun_proc.returncode


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2])
def test_signal_forwarding(testproj, signum):
    subcmd = ["__test_sleep_and_exit_on_signal"]
    run(["jumpthegun", "start", subcmd[0]], proj_path=testproj, check=True)
    try:
        proc: subprocess.Popen = run(["jumpthegun", "run", *subcmd], proj_path=testproj, background=True)
        assert proc.stdout.readline() == b"Sleeping...\n"
        assert proc.poll() is None
        proc.send_signal(signum)
        proc.wait(2)
        assert b"Received signal" in proc.stdout.read()
    finally:
        run(["jumpthegun", "stop", subcmd[0]], proj_path=testproj, check=True)


def run(cmd: list[str], proj_path: Path, background: bool = False, check: bool = False) -> subprocess.CompletedProcess[bytes] | subprocess.Popen:
    if background and check:
        raise ValueError("Must not set both background=True and check=True.")

    pass_through_env_vars = {
        key: value
        for key, value in os.environ.items()
        if re.fullmatch(r"TMPDIR|USER|XDG_.*", key)
    }

    bin_path = get_bin_path(proj_path).resolve()
    proc_kwargs = dict(
        cwd=str(proj_path),
        env={
            **pass_through_env_vars,
            "PATH": f"{str(bin_path)}:{os.getenv('PATH', '')}".strip(":"),
            "VIRTUAL_ENV": str(bin_path.parent),
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if background:
        return subprocess.Popen(cmd, **proc_kwargs)
    else:
        try:
            return subprocess.run(cmd, check=check, **proc_kwargs)
        except subprocess.CalledProcessError as proc_exc:
            if proc_exc.stdout:
                print("Stdout:")
                print(proc_exc.stdout.decode())
            if proc_exc.stdout:
                print("Stderr:")
                print(proc_exc.stderr.decode())
            raise
