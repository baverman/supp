import pytest
from textwrap import dedent

__builtins__['pytest'] = pytest

def sp(source):
    source = dedent(source)
    cursors = []
    parts = source.split(type(source)('|'))
    pos = 0
    for p in parts[:-1]:
        pos += len(p)
        cursors.append(pos)

    return [type(source)('').join(parts)] + cursors

