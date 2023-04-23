Jump the Gun
============
Make Python CLI tools win the speed race, by cheating!


# What?

Make Python CLI tools blazing fast, by entirely avoiding the time taken for
Python interpreter startup and module imports.


# Why?

CLI tools should be fast. Ideally, running them should be near-instant.

This is especially significant, for example, when running code linting and
formatting tools on just a few files in SCM hooks, such as via
[pre-commit](https://pre-commit.com/).


# Installation

Install JumpTheGun into any Python environment (Python >= 3.7):

```shell
pip install jumpthegun
```

Or use [pipx](https://pypa.github.io/pipx/):
```shell
pipx install jumpthegun
```


# Usage

Example:

```shell
jumpthegun run black --help

time black --help
time jumpthegun run black --help

time black --check .
time jumpthegun run black --check .
```

## With pre-commit

[pre-commit](https://pre-commit.com/) is awesome, but it makes commits slower.
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


# Copyright & License

Copyright 2022-2023 Tal Einat.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.


Version 3.90 of the filelock library is included in this codebase as-is. It is
made available under the terms of the Unlicense software license. See it's
LICENSE file for details.
