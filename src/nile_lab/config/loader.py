"""Load and validate lab.yaml. The YAML library choice is provisional (feature 3)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from nile_lab.config.models import LabConfig

DEFAULT_PATH = Path("/srv/nile-lab/lab.yaml")
ENV_VAR = "NILE_LAB_CONFIG"


class ConfigError(Exception):
    """Invalid or unreadable config. `problems` never contains input values."""

    def __init__(self, path: Path, problems: list[str]):
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: {len(problems)} problem(s)")


def resolve_path(cli_path: Path | None) -> Path:
    if cli_path is not None:
        return cli_path
    if env := os.environ.get(ENV_VAR):
        return Path(env)
    return DEFAULT_PATH


def load(path: Path) -> LabConfig:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(path, [f"cannot read file: {e.strerror}"]) from None
    except UnicodeDecodeError as e:
        raise ConfigError(path, [f"not valid UTF-8 at byte {e.start}"]) from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        raise ConfigError(path, [f"not valid YAML{where}"]) from None
    if not isinstance(data, dict):
        raise ConfigError(path, ["top level must be a mapping"])
    try:
        return LabConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(path, _describe(e)) from None


def _describe(e: ValidationError) -> list[str]:
    # include_input=False keeps secret values out of every message.
    out = []
    for err in e.errors(include_input=False, include_url=False):
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        msg = err["msg"].removeprefix("Value error, ")
        out += [f"{loc}: {line}" for line in msg.splitlines()]
    return out
