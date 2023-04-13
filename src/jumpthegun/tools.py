import importlib
from functools import reduce
from typing import Callable, Dict, Union

__all__ = [
    "get_tool_runner",
    "ToolExceptionBase",
    "InvalidToolName",
    "UnsupportedTool",
]


runners: Dict[str, Union[str, Callable[[], None]]] = {
    "black": "black:patched_main",
    "hatch": "hatch.cli:main",
    "flake8": "flake8.main.cli:main",
    "isort": "isort.main:main",
    "mypy": "mypy.__main__:console_entry",
    "pre-commit": "pre_commit.main:main",
    "pylint": "pylint:run_pylint",
    "__test_sleep_and_exit_on_signal": "jumpthegun.testutils:sleep_and_exit_on_signal",
}


class ToolExceptionBase(Exception):
    """Exception raised for CLI tool-related exceptions."""

    tool_name: str

    def __init__(self, tool_name) -> None:
        super().__init__(tool_name)
        self.tool_name = tool_name


class UnsupportedTool(ToolExceptionBase):
    """Exception raised for unsupported CLI tools."""

    def __str__(self) -> str:
        return f"Unsupported tool: {self.tool_name}"


class InvalidToolName(ToolExceptionBase):
    """Exception raised for unsupported CLI tools."""

    def __str__(self) -> str:
        return f"Invalid tool name: {self.tool_name}"


def get_tool_runner(tool_name: str) -> Callable[[], None]:
    """Get a runner function for a CLI tool."""
    tool_name = tool_name.strip().lower()
    if "/" in tool_name or "\\" in tool_name:
        raise InvalidToolName(tool_name=tool_name)
    try:
        runner = runners[tool_name]
    except KeyError:
        raise UnsupportedTool(tool_name=tool_name)

    module_name, function_name = runner.split(":")
    module = importlib.import_module(module_name)
    function = reduce(getattr, function_name.split("."), module)
    return function
