from supp.linter import lint
from .helpers import dedent


def test_check_syntax():
    s = dedent('''\
        def boo()
            pass
    ''')

    result = lint(None, s)
    assert result == [('E01', 'Invalid syntax', 1, 10)]


def test_name_usages():
    s = dedent('''\
        baz = 10
        def boo():
            _i = 0
            foo = 1
            boo = 1
            bar(foo)
    ''')

    result = lint(None, s)
    assert result == [
        ('E02', 'Undefined name: bar', 6, 4),
        ('W01', 'Unused name: boo', 5, 11)
    ]
