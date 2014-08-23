import pytest
from textwrap import dedent

__builtins__['pytest'] = pytest

def sp(source):
    source = dedent(source)
    cursors = []
    parts = source.split(type(source)('|'))
    pos = 0
    source = ''
    for p in parts[:-1]:
        pos += len(p)
        source += p
        line = source.count('\n') + 1
        column = pos - source.rfind('\n') - 1
        cursors.append((line, column))

    return [type(source)('').join(parts)] + cursors
