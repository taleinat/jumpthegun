import os
import textwrap

import pytest

from jumpthegun.tools import find_entrypoint_func_in_entrypoint_script


script1_code = textwrap.dedent('''\
    #!/nonexistent/path/to/fake/venv/bin/python
    # -*- coding: utf-8 -*-
    import re
    import sys
    from module_name.main import class_name
    if __name__ == '__main__':
        sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])
        sys.exit(class_name.method_name())
''')
script1_entrypoint_str = "module_name.main:class_name.method_name"

script2_code = textwrap.dedent('''\
    #!/nonexistent/path/to/fake/venv/bin/python
    import re
    import sys
    from module_name.submodule_name.main import func_name
    if __name__ == '__main__':
        sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])
        sys.exit(func_name())
''')
script2_entrypoint_str = "module_name.submodule_name.main:func_name"


@pytest.mark.parametrize(
    ["script_code", "entrypoint_str"],
    [
        (script1_code, script1_entrypoint_str),
        (script2_code, script2_entrypoint_str),
    ],
    ids=[
        "script1",
        "script2",
    ],
)
def test_find_entrypoint_func_in_entrypoint_script(monkeypatch, tmp_path, script_code, entrypoint_str):
    """Test parsing an entrypoint script.

    Such scripts are created by pip and other tools which use distlib.
    """
    script_name = "_testing_tool_name_"
    script_path = tmp_path / script_name
    script_path.write_text(script_code)
    script_path.chmod(0o777)
    monkeypatch.setenv('PATH', str(tmp_path.resolve()), prepend=os.pathsep)
    result = find_entrypoint_func_in_entrypoint_script(script_name)
    assert result == entrypoint_str


def test_find_entrypoint_func_in_entrypoint_script_nonexistent():
    """Test failing to find an entrypoint for a non-existent script."""
    assert find_entrypoint_func_in_entrypoint_script("DOES_NOT_EXIST") is None
