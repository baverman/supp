from ast import  With
import pytest

from supp.compat import PY2, HAS_VAR_TYPE_HINTS, HAS_WALRUS
from supp.name import AssignedName
from supp.project import Project

from .helpers import csp, nvalues, names_at

if not PY2:
    from ast import AsyncWith
    With = With, AsyncWith


def test_simple_flow():
    scope, p = csp('''\
        foo = 10
        |boo = 20
        |
    ''')

    assert nvalues(scope.names) == {'foo': 10, 'boo': 20}
    assert nvalues(names_at(scope, p[0])) == {'foo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 10, 'boo': 20}


def test_value_override():
    scope, p = csp('''\
        foo = 10
        foo = |20
        |
        foo + |boo
    ''')

    assert nvalues(scope.names) == {'foo': 20}
    assert nvalues(names_at(scope, p[0])) == {'foo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 20}
    assert nvalues(names_at(scope, p[2])) == {'foo': 20}


def test_simple_if():
    scope, p = csp('''\
        a = 10
        if True:
            b = 10
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 10}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'b': {10, 'undefined'}}


def test_if():
    scope, p = csp('''\
        a = 10
        if True:
            b = 10
            |c = 10
            |
        elif False:
            c = 20
        else:
            a = 30
            |b = 20
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 10}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'b': 10, 'c': 10}
    assert nvalues(names_at(scope, p[2])) == {'a': 30}
    assert nvalues(names_at(scope, p[3])) == {'a': 30, 'b': 20}
    assert nvalues(names_at(scope, p[4])) == {
        'a': {10, 30},
        'b': {10, 20, 'undefined'},
        'c': {10, 20, 'undefined'}
    }


def test_for_without_break():
    scope, p = csp('''\
        b = 10
        for a in [1, 2, 3]:
            |b = 20
            |
        else:
            c = 10
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 'listitem', 'b': {10, 20}}
    assert nvalues(names_at(scope, p[1])) == {'a': 'listitem', 'b': 20}
    assert nvalues(names_at(scope, p[2])) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}
    assert nvalues(names_at(scope, p[3])) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_for():
    scope, p = csp('''\
        async def foo():
            async for a in [1, 2, 3]:
                |
                pass
    ''')
    assert nvalues(names_at(scope, p[0])) == {'a': 'listitem', 'foo': 'func'}


def test_for_with_inner_try():
    scope, p = csp('''\
        for name in (1, 3):
            name(); |
            try:
                boo = 10
            except KeyError:
                pass
    ''')

    assert nvalues(names_at(scope, p[0])) == {'name': 'listitem', 'boo': {10, 'undefined'}}


def test_while_without_break():
    scope, p = csp('''\
        b = 10
        while True:
            |b = 20
            |
        else:
            c = 10
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'b': {10, 20}}
    assert nvalues(names_at(scope, p[1])) == {'b': 20}
    assert nvalues(names_at(scope, p[2])) == {'b': {10, 20}, 'c': 10}
    assert nvalues(names_at(scope, p[3])) == {'b': {10, 20}, 'c': 10}


def test_imports():
    scope, _p = csp('''\
        import os
        import os as so
        import os.path as ospath
        from os import path
        from os import path as opath
        from . import boo
        from .. import foo
        from .boo import bar, tar
    ''')

    assert nvalues(scope.names) == {
        'os': 'import:os',
        'so': 'import:os',
        'ospath': 'import:os.path',
        'path': 'import:os:path',
        'opath': 'import:os:path',
        'boo': 'import:.:boo',
        'foo': 'import:..:foo',
        'bar': 'import:.boo:bar',
        'tar': 'import:.boo:tar',
    }


def test_oneliners():
    scope, p = csp('''\
        import traceback;|
        a = 10;|
    ''')

    assert nvalues(names_at(scope, p[0])) == {'traceback': 'import:traceback'}
    assert nvalues(names_at(scope, p[1])) == {'traceback': 'import:traceback', 'a': 10}


def test_simple_try_except():
    scope, p = csp('''\
        try:
            a = 10
        except:
            |a = 20
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[1])) == {'a': {10, 20}}


def test_try_except():
    scope, p = csp('''\
        try:
            a = 10
        except ValueError as e:
            |a = 20
            |
        except Exception as ee:
            b = 10
            |
        else:
            c = 10
            |
        finally:
            d = 30
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': {10, 'undefined'}, 'e': 'ValueError'}
    assert nvalues(names_at(scope, p[1])) == {'a': 20, 'e': 'ValueError'}
    assert nvalues(names_at(scope, p[2])) == {'a': {10, 'undefined'}, 'b': 10, 'ee': 'Exception'}
    assert nvalues(names_at(scope, p[3])) == {'a': 10, 'c': 10}
    assert nvalues(names_at(scope, p[4])) == {
        'a': {10, 20, 'undefined'},
        'c': {10, 'undefined'},
        'b': {10, 'undefined'},
        'd': 30,
        'e': {'ValueError', 'undefined'},
        'ee': {'Exception', 'undefined'},
    }


def test_function_scope():
    scope, p = csp('''\
        a = 10
        @some.foo
        def foo(b):
            c = 10
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 'foo.arg', 'c': 10, 'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}
    assert scope.names['foo'].declared_at == (3, 4)


def test_empty_function_scope():
    scope, p = csp('''\
        def foo(boo):
            """Empty

            Boo
            """
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'foo': 'func'}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_function_scope():
    scope, p = csp('''\
        a = 10
        @some.foo
        async def foo(b):
            c = 10
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 'foo.arg', 'c': 10, 'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}
    assert scope.names['foo'].declared_at == (3, 10)


def test_parent_scope_var_masking():
    scope, p = csp('''\
        a = 10
        def foo():
            |a = 20
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}


def test_class_scope():
    scope, p = csp('''\
        a = 10
        @some.Boo
        class Boo:
            BOO = 10
            |
            def boo(self):
                b = 10
                |
            |
        |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'Boo': 'class', 'BOO': 10}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'Boo': 'class', 'self': 'boo.arg', 'b': 10}
    assert nvalues(names_at(scope, p[2])) == {'a': 10, 'Boo': 'class', 'boo': 'func', 'BOO': 10}
    assert nvalues(names_at(scope, p[3])) == {'a': 10, 'Boo': 'class'}
    assert scope.names['Boo'].declared_at == (3, 6)


def test_class_scope_reassign():
    scope, p = csp('''\
        boo = 10
        class Boo:
            boo = |boo
            |
    ''')

    assert nvalues(names_at(scope, p[0])) == {'Boo': 'class', 'boo': 10}
    assert nvalues(names_at(scope, p[1])) == {'Boo': 'class', 'boo': 'boo'}


def test_attr_assign():
    scope, _p = csp('''\
        foo.boo = 10
    ''')


def test_multiple_targest():
    scope, _p = csp('''\
        foo, boo = 1, 2
    ''')
    assert set(scope.names) == set(('boo', 'foo'))


def test_for_multiple_targest():
    scope, p = csp('''\
        for foo, boo in [1, 2]:
            |pass
    ''')
    assert set(names_at(scope, p[0])) == set(('boo', 'foo'))


def test_nested_funcs():
    scope, p = csp('''\
        def foo():
            a = 10
            def boo():
                b = 20
                |

            if True:
                a = 20
                b = 10
    ''')
    assert nvalues(names_at(scope, p[0])) == {
        'a': {10, 20},
        'b': 20,
        'boo': 'func',
        'foo': 'func'
    }


def test_one_line_scopes():
    scope, p = csp('''\
        def foo(): pass
        def boo(baz): return |10
        class bar: pass
        |
    ''')
    assert set(names_at(scope, p[0])) == {'foo', 'boo', 'bar', 'baz'}
    assert set(names_at(scope, p[1])) == {'foo', 'boo', 'bar'}


def test_multiline_expression():
    scope, p = csp('''\
        foo = 10
        (foo +
             |boo)
    ''')

    assert nvalues(names_at(scope, p[0])) == {'foo': 10}


def test_multiline_expression2():
    scope, p = csp('''\
        def foo(arg):
            return 'ArgumentName({}, {}, {})'.format(
                arg.name, |arg.location, arg.declared_at)
    ''')

    assert nvalues(names_at(scope, p[0])) == {'arg': 'foo.arg', 'foo': 'func'}


def test_lambda():
    scope, p = csp('''\
        a = 10
        f = lambda b: a + |a
    ''')
    assert nvalues(names_at(scope, p[0])) == {
        'a': 10,
        'b': 'lambda.arg',
        'f': 'lambda'
    }


def test_scope_levels():
    scope, p = csp('''\
        def boo():
            if name:
                return 10

        def foo(arg):
            return func(
                |arg)
    ''')
    assert nvalues(names_at(scope, p[0])) == {'arg': 'foo.arg', 'foo': 'func', 'boo': 'func'}


def test_vargs():
    scope, p = csp('''\
        @vargs
        def boo(*vargs):
            |pass
    ''')
    names = names_at(scope, p[0])
    assert nvalues(names) == {'vargs': 'boo.arg', 'boo': 'func'}
    assert names['vargs'].declared_at == (2, 9)


def test_kwargs():
    scope, p = csp('''\
        @kwargs
        def boo(**kwargs):
            |pass
    ''')
    names = names_at(scope, p[0])
    assert nvalues(names) == {'kwargs': 'boo.arg', 'boo': 'func'}
    assert names['kwargs'].declared_at == (2, 10)


@pytest.mark.skipif(PY2, reason='py3 only')
def test_default_args_in_the_middle():
    scope, p = csp('''\
        def boo(*args, foo=None, **kwargs):
            |pass
    ''')
    names = names_at(scope, p[0])
    assert nvalues(names) == {'kwargs': 'boo.arg', 'boo': 'func',
                              'foo': 'boo.arg', 'args': 'boo.arg'}


def test_list_comprehension():
    scope, p = csp('''\
        [|r for |r in (1, 2, 3)]
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}
    assert nvalues(names_at(scope, p[1])) == {}


def test_generator_comprehension():
    scope, p = csp('''\
        (|r for r in (1, 2, 3))
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_dict_comprehension():
    scope, p = csp('''\
        {1: |r for r in (1, 2, 3)}
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_set_comprehension():
    scope, p = csp('''\
        {|r for r in (1, 2, 3)}
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_with():
    scope, p = csp('''\
        with open('boo') as f:
            |pass
    ''')
    assert nvalues(names_at(scope, p[0])) == {'f': 'with'}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_with():
    scope, p = csp('''\
        async def foo():
            async with open('boo') as f:
                |pass
    ''')
    assert nvalues(names_at(scope, p[0])) == {'f': 'with', 'foo': 'func'}


def test_multi_assign():
    scope, p = csp('''\
        a = b = 10
        |
    ''')
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 10}


def test_visit_value_node_in_unsupported_assignments():
    scope, p = csp('''\
        foo.boo = lambda a: |a + 1
    ''')
    assert nvalues(names_at(scope, p[0])) == {'a': 'lambda.arg'}


def test_if_in_try_except():
    scope, p = csp('''\
        try:
            pass
        except Exception as e:
            if True:
                raise |e
        else:
            break
    ''')
    assert nvalues(names_at(scope, p[0])) == {'e': 'Exception'}


def test_global():
    scope, p = csp('''\
        def foo():
            global boo
            boo = 10

        def bar():
            |pass
        |
    ''')
    assert nvalues(names_at(scope, p[0])) == {'foo': 'func', 'bar': 'func', 'boo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 'func', 'bar': 'func'}


def test_deep_flow_shift():
    scope, p = csp('''\
        if True:
            if True:
                if True:
                    pass

        for boo in []:
            if False:
                continue
            if (True and
                    |boo):
                continue
    ''')
    assert nvalues(names_at(scope, p[0])) == {'boo': 'listitem'}


def test_nested_nest():
    scope, p = csp('''\
        if True:
            a = 10
            if True:
                b = 10
                if True:
                    c = 10
                    pass
        |    |    |    |
    ''')
    assert nvalues(names_at(scope, p[3])) == {'a': 10, 'b': 10, 'c': 10}
    assert nvalues(names_at(scope, p[2])) == {'a': 10, 'b': 10, 'c': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[0])) == {'a': {10, 'undefined'},
                                           'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}


def test_scope_shift_after_nested_flow():
    scope, p = csp('''\
        if True:
            if True:
                pass

        boo = 10
        print(); |boo
    ''')
    assert nvalues(names_at(scope, p[0])) == {'boo': 10}


def test_names_at_flow_start():
    scope, p = csp('''\
        def foo(boo):
            with |boo:
                pass
    ''')
    assert nvalues(names_at(scope, p[0])) == {'boo': 'foo.arg', 'foo': 'func'}


def test_lambda_in_gen_expression():
    scope, p = csp('''\
        [i for i in filter(lambda r: |r, [1,2,3])]
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'lambda.arg', 'i': {'func()', 'undefined'}}


def test_top_expression_region():
    scope, p = csp('''\
        if True:
            if True:
                pass

        boo = 10
        data = {
            'key': |boo
        }
    ''')
    assert nvalues(names_at(scope, p[0])) == {'boo': 10}


def test_multi_comprehensions():
    scope, p = csp('''\
        [x for x in [] for y in |x if |y if |x]
    ''')
    assert nvalues(names_at(scope, p[0])) == {'x': 'listitem'}
    assert nvalues(names_at(scope, p[1])) == {'x': 'listitem', 'y': 'x'}
    assert nvalues(names_at(scope, p[2])) == {'x': 'listitem', 'y': 'x'}


def test_nested_comprehensions():
    scope, p = csp('''\
        [[|r for r in |x] for x in []]
    ''')
    assert nvalues(names_at(scope, p[0])) == {'x': 'listitem', 'r': 'x'}
    assert nvalues(names_at(scope, p[1])) == {'x': 'listitem'}


def test_visit_decorator():
    scope, p = csp('''\
        @boo(|r for r in [])
        def foo():
            pass
    ''')
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_param_in_decorator():
    scope, p = csp('''\
        def decorator(func):
            @wraps(|func)
            def inner():
                pass
            return inner
    ''')
    assert nvalues(names_at(scope, p[0])) == {'decorator': 'func', 'func': 'decorator.arg'}


def test_flow_position_shoud_ignore_fake_flows():
    scope, p = csp('''\
        def foo(source):
            |source = [r for r in source.splitlines()]
            source = 'very long text to catch   region'.format(|source)
    ''')
    result = names_at(scope, p[1])
    assert result['source'].declared_at == p[0]


def test_nested_expression_regions():
    scope, p = csp('''\
        {r.id: (
            r.related_artists and list(r.related_artists) or [],
            |r.image_orig_width,
        ) for r in []}
    ''')
    result = names_at(scope, p[0])
    assert nvalues(result) == {'r': 'listitem'}


def test_import_name_locations():
    scope, _p = csp('''\
        import booga,foo,boo
        from module import (some,
                            bar)
    ''')
    names = scope.names
    assert names['boo'].declared_at == (1, 17)
    assert names['foo'].declared_at == (1, 13)
    assert names['some'].declared_at == (2, 20)
    assert names['bar'].declared_at == (3, 20)


def test_parent_names_through_loop():
    scope, p = csp('''\
        foo = 10
        for _ in []:
            pass
        |
    ''')
    names = names_at(scope, p[0])
    assert type(names['foo']) == AssignedName


def test_dotted_imports():
    scope, p = csp('''\
        import os.path
        |
    ''')
    names = names_at(scope, p[0])
    assert nvalues(names) == {'os': 'import:os'}


def test_star_imports():
    scope, p = csp('''\
        from os.path import *
        |
    ''')

    names = names_at(scope, p[0], project=Project())
    assert 'join' in names
    assert 'abspath' in names


def test_star_imports_in_func_scope():
    scope, p = csp('''\
        def foo():
            from os.path import *
            |
        |
    ''')

    project = Project()
    names = names_at(scope, p[0], project=project)
    assert 'join' in names
    assert 'abspath' in names

    names = names_at(scope, p[1], project=project)
    assert 'abspath' not in names


@pytest.mark.skipif(not HAS_VAR_TYPE_HINTS, reason='python>=3.6')
def test_var_type_hits():
    scope, p = csp('''\
        foo: int = 10
        boo: str
        |
    ''')

    names = names_at(scope, p[0])
    assert nvalues(names) == {'foo': 10}


@pytest.mark.skipif(not HAS_VAR_TYPE_HINTS, reason='python>=3.6')
def test_class_attr_type_hits():
    scope, p = csp('''\
        class Foo:
            foo: int = 10
            |
            boo: str
            |
    ''')

    names = names_at(scope, p[0])
    assert nvalues(names) == {'foo': 10, 'Foo': 'class'}

    names = names_at(scope, p[1])
    assert nvalues(names) == {'Foo': 'class', 'foo': 10}


@pytest.mark.skipif(not HAS_WALRUS, reason='python>=3.6')
def test_walrus():
    scope, p = csp('''\
        if boo := 10:
            |
            pass
    ''')
    names = names_at(scope, p[0])
    assert nvalues(names) == {'boo': 10}


# def test_boo():
#     scope = create_scope(open('/usr/lib/python2.7/posixpath.py').read())
#     print scope.flows[0]
#     assert False
