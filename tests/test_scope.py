import os
from ast import Lambda, With, Call, Subscript, Dict
import pytest

from supp.compat import iteritems, PY2, HAS_VAR_TYPE_HINTS, HAS_WALRUS
from supp.name import (AssignedName, UndefinedName, MultiName,
                       ImportedName, ArgumentName)
from supp.scope import SourceScope, FuncScope, ClassScope
from supp.project import Project
from supp.util import Source, print_dump, dump_flows
from supp.nast import extract, marked_flow

from .helpers import sp

if not PY2:
    from ast import AsyncWith
    With = With, AsyncWith


def test_simple_flow():
    source, p = sp('''\
        foo = 10
        |boo = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 10, 'boo': 20}
    assert nvalues(names_at(scope, p[0])) == {'foo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 10, 'boo': 20}


def test_value_override():
    source, p = sp('''\
        foo = 10
        foo = |20
        |
        foo + |boo
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 20}
    assert nvalues(names_at(scope, p[0])) == {'foo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 20}
    assert nvalues(names_at(scope, p[2])) == {'foo': 20}


def test_simple_if():
    source, p = sp('''\
        a = 10
        if True:
            b = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 10}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'b': {10, 'undefined'}}


def test_if():
    source, p = sp('''\
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

    scope = create_scope(source)
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
    source, p = sp('''\
        b = 10
        for a in [1, 2, 3]:
            |b = 20
            |
        else:
            c = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 'listitem', 'b': {10, 20}}
    assert nvalues(names_at(scope, p[1])) == {'a': 'listitem', 'b': 20}
    assert nvalues(names_at(scope, p[2])) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}
    assert nvalues(names_at(scope, p[3])) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_for():
    source, p = sp('''\
        async def foo():
            async for a in [1, 2, 3]:
                |
                pass
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 'listitem', 'foo': 'func'}


def test_for_with_inner_try():
    source, p = sp('''\
        for name in (1, 3):
            name(); |
            try:
                boo = 10
            except KeyError:
                pass
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'name': 'listitem', 'boo': {10, 'undefined'}}


def test_while_without_break():
    source, p = sp('''\
        b = 10
        while True:
            |b = 20
            |
        else:
            c = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'b': {10, 20}}
    assert nvalues(names_at(scope, p[1])) == {'b': 20}
    assert nvalues(names_at(scope, p[2])) == {'b': {10, 20}, 'c': 10}
    assert nvalues(names_at(scope, p[3])) == {'b': {10, 20}, 'c': 10}


def test_imports():
    source, _p = sp('''\
        import os
        import os as so
        import os.path as ospath
        from os import path
        from os import path as opath
        from . import boo
        from .. import foo
        from .boo import bar, tar
    ''')

    scope = create_scope(source)
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
    source, p = sp('''\
        import traceback;|
        a = 10;|
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'traceback': 'import:traceback'}
    assert nvalues(names_at(scope, p[1])) == {'traceback': 'import:traceback', 'a': 10}


def test_simple_try_except():
    source, p = sp('''\
        try:
            a = 10
        except:
            |a = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[1])) == {'a': {10, 20}}


def test_try_except():
    source, p = sp('''\
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

    scope = create_scope(source)
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
    source, p = sp('''\
        a = 10
        @some.foo
        def foo(b):
            c = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 'foo.arg', 'c': 10, 'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}
    assert scope.names['foo'].declared_at == (3, 4)


def test_empty_function_scope():
    source, p = sp('''\
        def foo(boo):
            """Empty

            Boo
            """
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'foo': 'func'}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_function_scope():
    source, p = sp('''\
        a = 10
        @some.foo
        async def foo(b):
            c = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 'foo.arg', 'c': 10, 'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}
    assert scope.names['foo'].declared_at == (3, 10)


def test_parent_scope_var_masking():
    source, p = sp('''\
        a = 10
        def foo():
            |a = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'foo': 'func'}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'foo': 'func'}


def test_class_scope():
    source, p = sp('''\
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

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'Boo': 'class', 'BOO': 10}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'Boo': 'class', 'self': 'boo.arg', 'b': 10}
    assert nvalues(names_at(scope, p[2])) == {'a': 10, 'Boo': 'class', 'boo': 'func', 'BOO': 10}
    assert nvalues(names_at(scope, p[3])) == {'a': 10, 'Boo': 'class'}
    assert scope.names['Boo'].declared_at == (3, 6)


def test_class_scope_reassign():
    source, p = sp('''\
        boo = 10
        class Boo:
            boo = |boo
            |
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'Boo': 'class', 'boo': 10}
    assert nvalues(names_at(scope, p[1])) == {'Boo': 'class', 'boo': 'boo'}


def test_attr_assign():
    source, _p = sp('''\
        foo.boo = 10
    ''')
    create_scope(source)


def test_multiple_targest():
    source, _p = sp('''\
        foo, boo = 1, 2
    ''')
    scope = create_scope(source)
    assert set(scope.names) == set(('boo', 'foo'))


def test_for_multiple_targest():
    source, p = sp('''\
        for foo, boo in [1, 2]:
            |pass
    ''')
    scope = create_scope(source)
    assert set(names_at(scope, p[0])) == set(('boo', 'foo'))


def test_nested_funcs():
    source, p = sp('''\
        def foo():
            a = 10
            def boo():
                b = 20
                |

            if True:
                a = 20
                b = 10
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {
        'a': {10, 20},
        'b': 20,
        'boo': 'func',
        'foo': 'func'
    }


def test_one_line_scopes():
    source, p = sp('''\
        def foo(): pass
        def boo(baz): return |10
        class bar: pass
        |
    ''')
    scope = create_scope(source)
    assert set(names_at(scope, p[0])) == {'foo', 'boo', 'bar', 'baz'}
    assert set(names_at(scope, p[1])) == {'foo', 'boo', 'bar'}


def test_multiline_expression():
    source, p = sp('''\
        foo = 10
        (foo +
             |boo)
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'foo': 10}


def test_multiline_expression2():
    source, p = sp('''\
        def foo(arg):
            return 'ArgumentName({}, {}, {})'.format(
                arg.name, |arg.location, arg.declared_at)
    ''')

    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'arg': 'foo.arg', 'foo': 'func'}


def test_lambda():
    source, p = sp('''\
        a = 10
        f = lambda b: a + |a
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {
        'a': 10,
        'b': 'lambda.arg',
        'f': 'lambda'
    }


def test_scope_levels():
    source, p = sp('''\
        def boo():
            if name:
                return 10

        def foo(arg):
            return func(
                |arg)
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'arg': 'foo.arg', 'foo': 'func', 'boo': 'func'}


def test_vargs():
    source, p = sp('''\
        @vargs
        def boo(*vargs):
            |pass
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'vargs': 'boo.arg', 'boo': 'func'}
    assert names['vargs'].declared_at == (2, 9)


def test_kwargs():
    source, p = sp('''\
        @kwargs
        def boo(**kwargs):
            |pass
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'kwargs': 'boo.arg', 'boo': 'func'}
    assert names['kwargs'].declared_at == (2, 10)


@pytest.mark.skipif(PY2, reason='py3 only')
def test_default_args_in_the_middle():
    source, p = sp('''\
        def boo(*args, foo=None, **kwargs):
            |pass
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'kwargs': 'boo.arg', 'boo': 'func',
                              'foo': 'boo.arg', 'args': 'boo.arg'}


def test_list_comprehension():
    source, p = sp('''\
        [|r for |r in (1, 2, 3)]
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}
    assert nvalues(names_at(scope, p[1])) == {}


def test_generator_comprehension():
    source, p = sp('''\
        (|r for r in (1, 2, 3))
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_dict_comprehension():
    source, p = sp('''\
        {1: |r for r in (1, 2, 3)}
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_set_comprehension():
    source, p = sp('''\
        {|r for r in (1, 2, 3)}
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_with():
    source, p = sp('''\
        with open('boo') as f:
            |pass
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'f': 'with'}


@pytest.mark.skipif(PY2, reason='py3 only')
def test_async_with():
    source, p = sp('''\
        async def foo():
            async with open('boo') as f:
                |pass
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'f': 'with', 'foo': 'func'}


def test_multi_assign():
    source, p = sp('''\
        a = b = 10
        |
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 10, 'b': 10}


def test_visit_value_node_in_unsupported_assignments():
    source, p = sp('''\
        foo.boo = lambda a: |a + 1
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'a': 'lambda.arg'}


def test_if_in_try_except():
    source, p = sp('''\
        try:
            pass
        except Exception as e:
            if True:
                raise |e
        else:
            break
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'e': 'Exception'}


def test_global():
    source, p = sp('''\
        def foo():
            global boo
            boo = 10

        def bar():
            |pass
        |
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'foo': 'func', 'bar': 'func', 'boo': 10}
    assert nvalues(names_at(scope, p[1])) == {'foo': 'func', 'bar': 'func'}


def test_deep_flow_shift():
    source, p = sp('''\
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
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'boo': 'listitem'}


def test_nested_nest():
    source, p = sp('''\
        if True:
            a = 10
            if True:
                b = 10
                if True:
                    c = 10
                    pass
        |    |    |    |
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[3])) == {'a': 10, 'b': 10, 'c': 10}
    assert nvalues(names_at(scope, p[2])) == {'a': 10, 'b': 10, 'c': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[1])) == {'a': 10, 'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}
    assert nvalues(names_at(scope, p[0])) == {'a': {10, 'undefined'},
                                           'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}


def test_scope_shift_after_nested_flow():
    source, p = sp('''\
        if True:
            if True:
                pass

        boo = 10
        print(); |boo
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'boo': 10}


def test_names_at_flow_start():
    source, p = sp('''\
        def foo(boo):
            with |boo:
                pass
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'boo': 'foo.arg', 'foo': 'func'}


def test_lambda_in_gen_expression():
    source, p = sp('''\
        [i for i in filter(lambda r: |r, [1,2,3])]
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'lambda.arg', 'i': {'func()', 'undefined'}}


def test_top_expression_region():
    source, p = sp('''\
        if True:
            if True:
                pass

        boo = 10
        data = {
            'key': |boo
        }
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'boo': 10}


def test_multi_comprehensions():
    source, p = sp('''\
        [x for x in [] for y in |x if |y if |x]
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'x': 'listitem'}
    assert nvalues(names_at(scope, p[1])) == {'x': 'listitem', 'y': 'x'}
    assert nvalues(names_at(scope, p[2])) == {'x': 'listitem', 'y': 'x'}


def test_nested_comprehensions():
    source, p = sp('''\
        [[|r for r in |x] for x in []]
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'x': 'listitem', 'r': 'x'}
    assert nvalues(names_at(scope, p[1])) == {'x': 'listitem'}


def test_visit_decorator():
    source, p = sp('''\
        @boo(|r for r in [])
        def foo():
            pass
    ''')
    scope = create_scope(source)
    assert nvalues(names_at(scope, p[0])) == {'r': 'listitem'}


def test_param_in_decorator():
    source, p = sp('''\
        def decorator(func):
            @wraps(|func)
            def inner():
                pass
            return inner
    ''')
    scope = create_scope(source, flow_graph=False)
    assert nvalues(names_at(scope, p[0])) == {'decorator': 'func', 'func': 'decorator.arg'}


def test_flow_position_shoud_ignore_fake_flows():
    source, p = sp('''\
        def foo(source):
            |source = [r for r in source.splitlines()]
            source = 'very long text to catch   region'.format(|source)
    ''')
    scope = create_scope(source)
    result = names_at(scope, p[1])
    assert result['source'].declared_at == p[0]


def test_nested_expression_regions():
    source, p = sp('''\
        {r.id: (
            r.related_artists and list(r.related_artists) or [],
            |r.image_orig_width,
        ) for r in []}
    ''')
    scope = create_scope(source)
    result = names_at(scope, p[0])
    assert nvalues(result) == {'r': 'listitem'}


def test_import_name_locations():
    source, _p = sp('''\
        import booga,foo,boo
        from module import (some,
                            bar)
    ''')
    scope = create_scope(source)
    names = scope.names
    assert names['boo'].declared_at == (1, 17)
    assert names['foo'].declared_at == (1, 13)
    assert names['some'].declared_at == (2, 20)
    assert names['bar'].declared_at == (3, 20)


def test_parent_names_through_loop():
    source, p = sp('''\
        foo = 10
        for _ in []:
            pass
        |
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert type(names['foo']) == AssignedName


def test_dotted_imports():
    source, p = sp('''\
        import os.path
        |
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'os': 'import:os'}


def test_star_imports():
    source, p = sp('''\
        from os.path import *
        |
    ''')

    scope = create_scope(source)
    names = names_at(scope, p[0], project=Project())
    assert 'join' in names
    assert 'abspath' in names


def test_star_imports_in_func_scope():
    source, p = sp('''\
        def foo():
            from os.path import *
            |
        |
    ''')

    project = Project()
    scope = create_scope(source)
    names = names_at(scope, p[0], project=project)
    assert 'join' in names
    assert 'abspath' in names

    names = names_at(scope, p[1], project=project)
    assert 'abspath' not in names


@pytest.mark.skipif(not HAS_VAR_TYPE_HINTS, reason='python>=3.6')
def test_var_type_hits():
    source, p = sp('''\
        foo: int = 10
        boo: str
        |
    ''')

    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'foo': 10}


@pytest.mark.skipif(not HAS_VAR_TYPE_HINTS, reason='python>=3.6')
def test_class_attr_type_hits():
    source, p = sp('''\
        class Foo:
            foo: int = 10
            |
            boo: str
            |
    ''')

    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'foo': 10, 'Foo': 'class'}

    names = names_at(scope, p[1])
    assert nvalues(names) == {'Foo': 'class', 'foo': 10}


@pytest.mark.skipif(not HAS_WALRUS, reason='python>=3.6')
def test_walrus():
    source, p = sp('''\
        if boo := 10:
            |
            pass
    ''')
    scope = create_scope(source)
    names = names_at(scope, p[0])
    assert nvalues(names) == {'boo': 10}


# def test_boo():
#     scope = create_scope(open('/usr/lib/python2.7/posixpath.py').read())
#     print scope.flows[0]
#     assert False


def create_scope(source, filename=None, debug=False, flow_graph=False):
    source = Source(source, filename)
    (debug or os.environ.get('DEBUG')) and print_dump(source.tree)
    scope = SourceScope(source)
    scope.parent = None
    extract(source.tree, scope.flow)
    flow_graph or os.environ.get('FLOW_GRAPH') and dump_flows(scope, '/tmp/scope-dump.dot')
    return scope


def names_at(scope, p, project=None, debug=False):
    scope = scope.with_mark(p, debug)
    scope.parent = None
    debug and print_dump(scope.source.tree)
    extract(scope.source.tree, scope.flow)
    flow = marked_flow(scope)
    if project:
        scope.resolve_star_imports(project)
    import os
    if os.environ.get('PDB'):
        import ipdb; ipdb.set_trace()
    return flow.names_at(p)


def get_value(name):
    if isinstance(name, AssignedName):
        if isinstance(name.value_node, Lambda):
            return 'lambda'
        if isinstance(name.value_node, With):
            return 'with'
        if isinstance(name.value_node, Call):
            return 'func()'
        if isinstance(name.value_node, Subscript):
            return 'item[]'
        if isinstance(name.value_node, Dict):
            return '{}'
        if name.value_node is None:
            return 'none'
        if hasattr(name.value_node, 'elts'):
            return 'listitem'
        if hasattr(name.value_node, 'id'):
            return name.value_node.id
        return name.value_node.n
    elif isinstance(name, UndefinedName):
        return 'undefined'
    elif isinstance(name, MultiName):
        return set(get_value(r) for r in name.alt_names)
    elif isinstance(name, ImportedName):
        if name.mname:
            return 'import:{0.module}:{0.mname}'.format(name)
        else:
            return 'import:{0.module}'.format(name)
    elif isinstance(name, ArgumentName):
        return '{}.arg'.format(name.func.name, name.name)
    elif isinstance(name, FuncScope):
        return 'func'
    elif isinstance(name, ClassScope):
        return 'class'
    else:
        raise Exception('Unknown name type', name, type(name))


def nvalues(names):
    return {k: get_value(v) for k, v in iteritems(names)}
