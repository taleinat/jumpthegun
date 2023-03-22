import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if sys.version_info >= (3, 11):
    try:
        import tomllib
    except ImportError:
        # Help users on older alphas
        if not TYPE_CHECKING:
            import tomli as tomllib
else:
    import tomli as tomllib


def get_tool_names(start_path: Path) -> List[str]:
    """Get the names of tools configured for use in this project.

    Currently only pyproject.toml configurations and .flake8 are supported.
    """
    # TODO: Support pre-commit.

    project_root_path = find_project_root(start_path)
    if project_root_path is None:
        return []

    tool_names = []

    pyproject_toml_path = get_pyproject_toml(project_root_path)
    if pyproject_toml_path is not None:
        try:
            pyproject_tool_names = read_tool_names_from_pyproject_toml(
                pyproject_toml_path
            )
        except tomllib.TOMLDecodeError as exc:
            raise Exception("Failed reading tool names from pyproject.toml.") from exc
        tool_names.extend(pyproject_tool_names)

    dot_flake8_file_path = project_root_path / ".flake8"
    if dot_flake8_file_path.is_file():
        tool_names.append("flake8")

    return tool_names


def get_pyproject_toml(project_root_path: Path) -> Optional[Path]:
    """Find the path of a pyproject.toml if it exists."""
    if project_root_path is None:
        return None
    path_pyproject_toml = project_root_path / "pyproject.toml"
    if path_pyproject_toml.is_file():
        return path_pyproject_toml
    return None


def find_project_root(start_path: Path) -> Optional[Path]:
    """Find the root directory of a project."""
    dir_paths_to_check = list(start_path.parents)
    if start_path.is_dir():
        dir_paths_to_check.insert(0, start_path)
    for dir_path in dir_paths_to_check:
        if (dir_path / "pyproject.toml").is_file():
            return dir_path
        elif (dir_path / ".git").exists():
            return dir_path
        elif (dir_path / ".hg").is_dir():
            return dir_path


def read_tool_names_from_pyproject_toml(pyproject_toml_path: Path) -> List[str]:
    """Parse a pyproject toml file, pulling out names of defined tools."""
    with open(pyproject_toml_path, "rb") as f:
        pyproject_cfg = tomllib.load(f)
    tool_keys = list(pyproject_cfg.get("tool", {}).keys())
    return [key.replace("-", "_") for key in tool_keys]
