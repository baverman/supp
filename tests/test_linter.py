from supp.project import Project
from supp.linter import lint

from .helpers import dedent


def tlint(source, project=None):
    return lint(project, dedent(source))


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


def test_unused_imports():
    result = tlint('''\
        import os
    ''')
    assert strip(result) == [('W02', 'Unused import: os', 1, 7)]


def test_future_imports():
    result = tlint('''\
        from __future__ import print_function
    ''')
    assert not result


def test_star_imports():
    result = tlint('''\
        from os.path import *
    ''', Project())
    assert not result
