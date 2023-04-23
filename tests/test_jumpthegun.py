import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Union

import pytest


def get_bin_path(project_path: Path) -> Path:
    venv_path = project_path.with_name(project_path.name + "_venv")
    bin_dir_name = "Scripts" if sys.platform == "win32" else "bin"
    return venv_path / bin_dir_name


@pytest.fixture
def testproj(request, testproj_with_jumpthegun, testproj_without_jumpthegun) -> Path:
    testproj_name = getattr(request, "param", "testproj_without_jumpthegun")
    if testproj_name == "testproj_with_jumpthegun":
        return testproj_with_jumpthegun
    elif testproj_name == "testproj_without_jumpthegun":
        return testproj_without_jumpthegun


@pytest.fixture(scope="session")
def testproj_with_jumpthegun() -> Path:
    return _setup_test_project("testproj_with_jumpthegun", with_jumpthegun=True)


@pytest.fixture(scope="session")
def testproj_without_jumpthegun() -> Path:
    return _setup_test_project("testproj_without_jumpthegun", with_jumpthegun=False)


def _setup_test_project(name: str, with_jumpthegun: bool) -> Path:
    root_dir = Path(__file__).parent.parent
    testenvs_dir = root_dir / ".testenvs"
    testenvs_dir.mkdir(exist_ok=True)
    ver_dir = testenvs_dir / sys.version.split()[0]
    ver_dir.mkdir(exist_ok=True)

    proj_dir = ver_dir / name
    if not proj_dir.exists():
        sources_dir = Path(__file__).parent / "testproj"
        shutil.copytree(sources_dir, proj_dir)
        venv_path = get_bin_path(proj_dir).parent
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path.resolve())],
            check=True,
        )
        bin_path = get_bin_path(proj_dir)
        if with_jumpthegun:
            # Need pip >= 21.3 for editable installation without setup.py.
            # See: https://pip.pypa.io/en/stable/news/#v21-3
            subprocess.run(
                [str(bin_path / "pip"), "install", "--upgrade", "pip >= 21.3"],
                cwd=str(root_dir),
                check=True,
            )
        subprocess.run(
            [str(bin_path / "pip"), "install", "black", "flake8", "isort"],
            cwd=str(root_dir),
            check=True,
        )
        if with_jumpthegun:
            subprocess.run(
                [str(bin_path / "pip"), "install", "-e", "."],
                cwd=str(root_dir),
                check=True,
            )
        sleep_and_exit_on_signal_script = textwrap.dedent(
            """\
            #!/usr/bin/env python
            import jumpthegun.testutils

            jumpthegun.testutils.sleep_and_exit_on_signal()
            """
        )
        script_path = bin_path / "__test_sleep_and_exit_on_signal"
        script_path.write_text(sleep_and_exit_on_signal_script)
        script_path.chmod(0o755)

    return proj_dir


@pytest.mark.parametrize(
    "testproj",
    ["testproj_with_jumpthegun", "testproj_without_jumpthegun"],
    ids=["testproj_with_jumpthegun", "testproj_without_jumpthegun"],
    indirect=True,
)
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
        proc1 = run(
            ["jumpthegun", "run", "--no-autorun", *tool_cmd], proj_path=testproj
        )
        proc2 = run(["jumpthegun", "run", *tool_cmd], proj_path=testproj)
    finally:
        run(["jumpthegun", "stop", tool_cmd[0]], proj_path=testproj, check=True)

    assert proc1.stdout == without_jumpthegun_proc.stdout
    assert proc1.stderr == without_jumpthegun_proc.stderr
    assert proc1.returncode == without_jumpthegun_proc.returncode

    assert proc2.stdout == without_jumpthegun_proc.stdout
    assert proc2.stderr == without_jumpthegun_proc.stderr
    assert proc2.returncode == without_jumpthegun_proc.returncode


def test_jumpthegun_autorun(testproj):
    tool_cmd = ["flake8"]

    without_jumpthegun_proc = run(tool_cmd, proj_path=testproj)
    assert without_jumpthegun_proc.returncode != 0

    try:
        proc1 = run(
            ["jumpthegun", "run", "--no-autorun", *tool_cmd], proj_path=testproj
        )
        proc2 = run(["jumpthegun", "run", *tool_cmd], proj_path=testproj)
        proc3 = run(
            ["jumpthegun", "run", "--no-autorun", *tool_cmd], proj_path=testproj
        )
    finally:
        run(["jumpthegun", "stop", tool_cmd[0]], proj_path=testproj, check=True)

    assert proc1.stdout == without_jumpthegun_proc.stdout
    assert proc1.stderr == without_jumpthegun_proc.stderr
    assert proc1.returncode == without_jumpthegun_proc.returncode

    assert proc2.stdout == without_jumpthegun_proc.stdout
    assert proc2.stderr == without_jumpthegun_proc.stderr
    assert proc2.returncode == without_jumpthegun_proc.returncode

    assert proc3.stdout == without_jumpthegun_proc.stdout
    assert proc3.stderr == without_jumpthegun_proc.stderr
    assert proc3.returncode == without_jumpthegun_proc.returncode


@pytest.mark.parametrize(
    "testproj",
    ["testproj_with_jumpthegun", "testproj_without_jumpthegun"],
    ids=["testproj_with_jumpthegun", "testproj_without_jumpthegun"],
    indirect=True,
)
@pytest.mark.parametrize(
    "signum", [signal.SIGINT, signal.SIGTERM, signal.SIGUSR1, signal.SIGUSR2]
)
def test_signal_forwarding(testproj, signum):
    subcmd = ["__test_sleep_and_exit_on_signal"]
    run(["jumpthegun", "start", subcmd[0]], proj_path=testproj, check=True)
    try:
        proc: subprocess.Popen = run(
            ["jumpthegun", "run", "--no-autorun", *subcmd],
            proj_path=testproj,
            background=True,
        )
        assert proc.stdout.readline() == b"Sleeping...\n"
        assert proc.poll() is None
        proc.send_signal(signum)
        proc.wait(2)
        assert b"Received signal" in proc.stdout.read()
    finally:
        run(["jumpthegun", "stop", subcmd[0]], proj_path=testproj, check=True)


def run(
    cmd: List[str], proj_path: Path, background: bool = False, check: bool = False
) -> Union[subprocess.CompletedProcess, subprocess.Popen]:
    if background and check:
        raise ValueError("Must not set both background=True and check=True.")

    pass_through_env_vars = {
        key: value
        for key, value in os.environ.items()
        if re.fullmatch(r"HOME|TMPDIR|USER|XDG_.*", key)
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
