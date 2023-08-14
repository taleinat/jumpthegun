import os
from dataclasses import dataclass
from typing import Dict, Set

all = [
    "EnvVarsDiff",
    "apply_env_with_diff",
    "calc_env_diff",
]


@dataclass
class EnvVarsDiff:
    changed: Dict[str, str]
    deleted: Set[str]


def calc_env_diff(before: Dict[str, str], after: Dict[str, str]) -> EnvVarsDiff:
    changed = dict(set(after.items()) - set(before.items()))
    deleted = set(before) - set(after)
    return EnvVarsDiff(changed=changed, deleted=deleted)


def apply_env_with_diff(env: Dict[str, str], diff: EnvVarsDiff) -> None:
    for var_name in diff.deleted:
        env.pop(var_name, None)
    env.update(diff.changed)
    for env_var_name in set(os.environ) - set(env):
        del os.environ[env_var_name]
    os.environ.update(env)
