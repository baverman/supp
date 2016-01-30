from supp.linter import lint
from .helpers import dedent


def tlint(source):
    return lint(None, dedent(source))


def strip(result):
    return [r[:4] for r in result]


def test_check_syntax():
    result = tlint('''\
        def boo()
            pass
    ''')

    assert strip(result) == [('E01', 'invalid syntax', 1, 10)]


def test_name_usages():
    result = tlint('''\
        baz = 10
        def boo():
            _i = 0
            foo = 1
            boo = 1
            bar(foo)
    ''')

    assert strip(result) == [
        ('E02', 'Undefined name: bar', 6, 4),
        ('W01', 'Unused name: boo', 5, 4)
    ]


def test_usage_with_multiflows():
    result = tlint('''\
        def boo():
            foo = 10
            while True:
                pass
            return foo
    ''')
    assert not result


def test_ignore_unused_args_in_methods():
    result = tlint('''\
        class Boo:
            def foo(self, arg):
                pass
    ''')
    assert not result
