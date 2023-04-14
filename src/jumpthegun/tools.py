import importlib
import re
import shutil
import textwrap
from functools import reduce
from pathlib import Path
from typing import Callable, Dict

__all__ = [
    "get_tool_entrypoint",
    "find_entrypoint_func_in_entrypoint_script",
    "ToolExceptionBase",
    "InvalidToolName",
    "UnsupportedTool",
]


runners: Dict[str, str] = {
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


def get_tool_entrypoint(tool_name: str) -> Callable[[], None]:
    """Get an entrypoint function for a CLI tool."""
    tool_name = tool_name.strip().lower()
    if "/" in tool_name or "\\" in tool_name:
        raise InvalidToolName(tool_name=tool_name)

    entrypoint_str = runners.get(tool_name)
    if entrypoint_str is None:
        entrypoint_str = find_entrypoint_func_in_entrypoint_script(tool_name)
        if entrypoint_str is None:
            raise UnsupportedTool(tool_name=tool_name)

    module_name, function_name = entrypoint_str.split(":")
    module = importlib.import_module(module_name)
    function = reduce(getattr, function_name.split("."), module)
    return function


SCRIPT_ENCODING_HEADER_RE = re.compile(
    br'^#\s*-\*- coding: ([a-zA-Z0-9._-]+) -\*-\s*$',
    re.MULTILINE,
)
# See distlib: https://github.com/pypa/distlib/blob/05375908c1b2d6b0e74bdeb574569d3609db9f56/distlib/scripts.py#L43-L50
ENTRYPOINT_SCRIPT_DISTLIB_TEMPLATE = textwrap.dedent(r'''
    import re
    import sys
    from %(module)s import %(import_name)s
    if __name__ == '__main__':
        sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
        sys.exit(%(func)s())
    ''')[1:]
ENTRYPOINT_SCRIPT_TEMPLATES = [
    ENTRYPOINT_SCRIPT_DISTLIB_TEMPLATE,
    # NOTE: For handling entrypoint script that's based off distlib, but has double quote instead.
    #       E.g. `sqlfluff` is one such library with said script template.
    ENTRYPOINT_SCRIPT_DISTLIB_TEMPLATE.replace("'", '"')
]
ENTRYPOINT_SCRIPT_RE_LIST = [
    re.compile(
        re.sub(
            re.escape(re.escape('%(')) + r'(\w+)' + re.escape(re.escape(')s')),
            r'(?P<\1>(?:\\w|\\.)+)',
            re.escape(template),
        ),
        re.IGNORECASE,
    )
    for template in ENTRYPOINT_SCRIPT_TEMPLATES
]


def find_entrypoint_func_in_entrypoint_script(tool_name: str) -> str | None:
    # Search for the executable.
    executable_path = shutil.which(tool_name)
    if executable_path is None:
        return None

    code_bytes = Path(executable_path).read_bytes()

    # Decode unicode.
    try:
        if encoding_match := SCRIPT_ENCODING_HEADER_RE.search(code_bytes):
            encoding = encoding_match.group(1).decode('ascii')
        else:
            encoding = "utf-8"
        code = code_bytes.decode(encoding)
    except UnicodeDecodeError:
        # TODO: Warn
        return None

    # Try to find an entrypoint function in the script's code.
    for entrypoint_script_re in ENTRYPOINT_SCRIPT_RE_LIST:
        if entrypoint_script_match := entrypoint_script_re.search(code):
            groupdict = entrypoint_script_match.groupdict()
            return f"{groupdict['module']}:{groupdict['func']}"
