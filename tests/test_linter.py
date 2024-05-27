import os
import pytest

from supp.project import Project
from supp.linter import lint
from supp.compat import PY2

from .helpers import dedent


def tlint(source, project=None):
    return lint(project, dedent(source), debug='DEBUG' in os.environ)


def strip(result):
    return [r[:4] for r in result]


def test_check_syntax():
    result = tlint('''\
        def boo()
            pass
    ''')

    result = strip(result)
    assert (result == [('E01', 'invalid syntax', 1, 10)]
           or result == [('E01', "expected ':'", 1, 10)])


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


@pytest.mark.xfail
def test_possible_undefined_name():
    result = tlint('''\
        if True:
            baz = 10
        print(baz)
    ''')
    assert result


def test_escape_flow():
    result = tlint('''\
        try:
            baz = 10
        except:
            raise
        print(baz)
    ''')
    assert not result


def test_default_args():
    result = tlint('''\
        baz = 10
        def boo(foo=baz):
            foo()
    ''')

    assert strip(result) == []


def test_attribute_assign():
    result = tlint('''\
        n = 10
        def boo():
            n.attr = 10
    ''')

    assert strip(result) == []


def test_names_in_except():
    result = tlint('''\
        def boo():
            n = 10
            try:
                pass
            except n:
                pass
    ''')

    assert strip(result) == []


def test_names_in_class_bases():
    result = tlint('''\
        boo = 10
        class Boo(boo):
            pass
    ''')

    assert strip(result) == []


def test_names_in_dict_comprehension():
    result = tlint('''\
        def foo():
            {k: v for k, v in {}}
    ''')

    assert strip(result) == []


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


def test_locals_usage():
    result = tlint('''\
        def boo():
            bar = 10
            return locals()
    ''')
    assert not result


def test_lambda_with_default_args():
    result = tlint('''\
        lambda min=None: min
    ''')
    assert not result


def test_qualified_imports():
    result = tlint('''\
        import logging.config
        import logging.handlers
    ''')
    assert strip(result) == [('W02', 'Unused import: logging', 1, 7),
                             ('W02', 'Unused import: logging', 2, 7)]

    result = tlint('''\
        import logging.config
        import logging.handlers
        logging.foo()
    ''')
    assert not result


@pytest.mark.skipif(PY2, reason='py3 only')
def test_annotations():
    result = tlint('''\
        foo = "10"
        boo = 20
        goo = 10
        def boo(bar:foo, *, baz:boo) -> goo:
            print(bar, baz)
    ''')
    assert not result


@pytest.mark.skipif(PY2, reason='py3 only')
def test_start_deconstruct():
    result = tlint('''\
        result = {boo: foo for *boo, foo in ['123']}
    ''')
    assert not result


@pytest.mark.skipif(PY2, reason='py3 only')
def test_args_kwarrgs_annotations():
    result = tlint('''\
        from module import T, P
        def boo(*args: T, **kwargs: P):
            print(args, kwargs)
    ''')
    assert not result
