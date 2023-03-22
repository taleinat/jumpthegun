import os
import sys


def foo() -> str:
    return "foo" + os.sep + sys.getdefaultencoding()
