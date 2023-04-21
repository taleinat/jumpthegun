import pytest

from jumpthegun.tools import ToolExceptionBase, get_tool_entrypoint


def test_find_pip():
    """Test failing to find an entrypoint for a non-existent script."""
    assert callable(get_tool_entrypoint("pip").load())


def test_find_nonexistent_entrypoint():
    """Test failing to find an entrypoint for a non-existent script."""
    with pytest.raises(ToolExceptionBase):
        get_tool_entrypoint("DOES_NOT_EXIST")
