Jump the Gun
============
Make Python CLI tools win the speed race, by cheating!

<a href="https://github.com/taleinat/jumpthegun/actions"><img alt="Actions Status" src="https://github.com/taleinat/jumpthegun/actions/workflows/main.yml/badge.svg"></a>
<a href="https://pypi.org/project/jumpthegun/"><img alt="PyPI" src="https://img.shields.io/pypi/v/jumpthegun"></a>
<a href="https://pepy.tech/project/jumpthegun"><img alt="Downloads" src="https://pepy.tech/badge/jumpthegun"></a>
<a href="https://github.com/taleinat/jumpthegun/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/github/license/taleinat/jumpthegun"></a>

```shell
# In any Python (>= 3.7) environment:
pip install jumpthegun

# For any CLI tool written in Python (>= 3.7):
jumpthegun run <cli-tool> [...]

# Example:
jumpthegun run black --check .

# More details:
jumpthegun --help
```


## Why?

CLI tools should be fast. Ideally, running them should be near-instant.

This is especially significant, for example, when running code linting and
formatting tools on just a few files while developing.


## How?

✨ Magic! ✨

JumpTheGun makes Python CLI tools start very fast, by entirely avoiding the
time taken for Python interpreter startup and module imports.

It works by:

1. Running a daemon process in the background for each CLI tool.  This
   initializes Python and imports the CLI tool's code in advance.
2. The daemon listens on a local TCP socket and uses fork to quickly create
   sub-processes with everything already initialized.
3. The `jumpthegun` command is implemented as a Bash script which connects to
   the daemon, passes the command-line arguments, and then passes input and
   output back and forth.

Some juicy details:

* Communication is done using a custom protocol, suitable for a simple
  implementation in Bash.
* `jumpthegun run` works even if a daemon is not already running; it will run
  a new background daemon in this case.
* JumpTheGun daemons have a timeout, so after a period of inactivity the
  daemon will exit.  The default timeout is 4 hours.  This is configurable via
  the config file; see [Configuration](#configuration).
* JumpTheGun needs to import a CLI tool's code and find which function to call
  to run it.  It gets that info inspecting the tool's entrypoint, as per the
  [PyPA Specification](https://packaging.python.org/en/latest/specifications/entry-points/),
  via `importlib.metadata.entry_points()`.
* To be able to run CLI tools installed in a different Python environment,
  JumpTheGun finds the Python interpreter used by the CLI tool, and if
  JumpTheGun isn't available in it, it runs that Python with PYTHONPATH set
  to include an additional directory with a copy of JumpTheGun's code.


## Configuration

The config file is named `jumpthegun.json`.  It is searched for in the
following locations, in order:
1. `$XDG_CONFIG_HOME`
2. `~/.config/`

The top-level object should be a mapping.  The following keys are supported:

* `idle_timeout_seconds`: Period with no activity after which the daemon exits.
  Default: 4 hours.


## Caveats

* JumpTheGun is in early stages of development.  It works for me; beyond that
  I can make no promises.  Every detail is likely to change in the future.
* Windows is not supported.
* Uses fork, with all of its caveats.  For example, tools that run background
  threads during module import will break.  JumpTheGun does not check for such
  issues.
* Uses local TCP sockets, so firewalls, VPNs etc. may cause issues.
* Does not support running standalone Python scripts which aren't installed
  as part of a package.
* Tested with Python 3.7 to 3.11, with x86-64 Ubuntu 20.04 and recent macOS on
  an ARM Mac.
* Requires having Bash installed.


## Using with pre-commit

[pre-commit](https://pre-commit.com/) is awesome, but running linters in
pre-commit hooks makes commits slower, even when running only on staged files.
JumpTheGun fixes that!

Example config (`.pre-commit-config.yaml`):
```yaml
repos:
- repo: https://github.com/PyCQA/flake8
  rev: 6.0.0
  hooks:
  - id: flake8
    entry: jumpthegun run flake8
    additional_dependencies:
    - jumpthegun
```

You may need to run `pre-commit install --install-hooks` if you've changed the
config in an existing working copy of a project.

Then, edit your `.git/hooks/pre-commit` and make this change:

```shell
if [ -x "$INSTALL_PYTHON" ]; then
    #exec "$INSTALL_PYTHON" -mpre_commit "${ARGS[@]}"
    exec jumpthegun run pre-commit "${ARGS[@]}"
```


## Copyright & License

Copyright 2022-2023 Tal Einat.

Licensed under [the MIT License](LICENSE).


Version 3.90 of the filelock library is included in this codebase as-is. It is
made available under the terms of the Unlicense software license. See it's
LICENSE file for details.
