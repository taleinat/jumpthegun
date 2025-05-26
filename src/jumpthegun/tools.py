import sys
from typing import Dict, cast

if sys.version_info < (3, 8):
    from importlib_metadata import EntryPoint, entry_points
else:
    from importlib.metadata import EntryPoint, entry_points

__all__ = [
    "get_tool_entrypoint",
    "ToolExceptionBase",
    "EntrypointNotFound",
    "MultipleEntrypointFound",
]


testing_tools: Dict[str, str] = {
    "__test_sleep_and_exit_on_signal": "jumpthegun.testutils:sleep_and_exit_on_signal",
}

well_known_tools: Dict[str, str] = {
    "aws": "awscli.clidriver:main",
}

all_known_tools = {**well_known_tools, **testing_tools}


class ToolExceptionBase(Exception):
    """Exception raised for CLI tool-related exceptions."""

    tool_name: str

    def __init__(self, tool_name) -> None:
        super().__init__(tool_name)
        self.tool_name = tool_name


class EntrypointNotFound(ToolExceptionBase):
    """Exception raised for unsupported CLI tools."""

    def __str__(self) -> str:
        return f"Console entrypoint not found: {self.tool_name}"


class MultipleEntrypointFound(ToolExceptionBase):
    """Exception raised for unsupported CLI tools."""

    def __str__(self) -> str:
        return f"Multiple console entrypoints: {self.tool_name}"


def get_tool_entrypoint(tool_name: str) -> EntryPoint:
    """Get an entrypoint function for a CLI tool."""
    tool_entrypoint_str = all_known_tools.get(tool_name)
    if tool_entrypoint_str is not None:
        entrypoint = EntryPoint(
            name=tool_name,
            value=tool_entrypoint_str,
            group="console_scripts",
        )
        return entrypoint

    entrypoints: tuple[EntryPoint, ...]
    all_entrypoints = entry_points()
    if hasattr(all_entrypoints, "select"):
        entrypoints = cast(
            tuple[EntryPoint, ...],
            all_entrypoints.select(name=tool_name, group="console_scripts"),
        )
    else:
        entrypoints = tuple(
            ep for ep in all_entrypoints["console_scripts"] if ep.name == tool_name
        )

    if not entrypoints:
        raise EntrypointNotFound(tool_name)
    elif len(entrypoints) == 1:
        return next(iter(entrypoints))
    else:
        raise MultipleEntrypointFound(tool_name)
