import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class JumpTheGunConfig:
    idle_timeout_seconds: Optional[int] = 4 * 60 * 60  # 4 hours

    def __post_init__(self):
        if self.idle_timeout_seconds is None:
            pass
        elif isinstance(self.idle_timeout_seconds, int):
            if self.idle_timeout_seconds <= 0:
                raise ValueError("idle_timeout_seconds must be positive.")
        else:
            raise TypeError("idle_timeout_seconds must be an int or None.")


def read_config() -> JumpTheGunConfig:
    config_dir = get_xdg_config_dir()
    if not config_dir.exists():
        return JumpTheGunConfig()
    config_file = config_dir / "jumpthegun.json"
    if not config_file.exists():
        return JumpTheGunConfig()
    with config_file.open(encoding="utf-8") as f:
        config_data = json.load(f)
    config = JumpTheGunConfig(**config_data)
    return config


def get_xdg_config_dir() -> Path:
    env_var = os.environ.get("XDG_CONFIG_HOME")
    if env_var:
        return Path(env_var)
    return Path.home() / ".config"
