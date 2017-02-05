from ast import Lambda, With, Call, Subscript, Dict

from supp.compat import iteritems
from supp.name import (AssignedName, UndefinedName, MultiName,
                       ImportedName, ArgumentName)
from supp.scope import FuncScope, ClassScope
from supp.astwalk import Extractor
from supp.project import Project
from supp.util import Source, print_dump, dump_flows

from .helpers import sp


def create_scope(source, filename=None, debug=False, flow_graph=False):
    e = Extractor(Source(source, filename))
    debug and print_dump(e.tree)
    e.scope.parent = None
    scope = e.process()
    flow_graph and dump_flows(scope, '/tmp/scope-dump.dot')
    return scope


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
        raise Exception('Unknown name type', name)


def nvalues(names):
    return {k: get_value(v) for k, v in iteritems(names)}


def test_simple_flow():
    source, p1, p2 = sp('''\
        foo = 10
        |boo = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 10, 'boo': 20}
    assert nvalues(scope.names_at(p1)) == {'foo': 10}
    assert nvalues(scope.names_at(p2)) == {'foo': 10, 'boo': 20}


def test_value_override():
    source, p1, p2, p3 = sp('''\
        foo = 10
        foo = |20
        |
        foo + |boo
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 20}
    assert nvalues(scope.names_at(p1)) == {'foo': 10}
    assert nvalues(scope.names_at(p2)) == {'foo': 20}
    assert nvalues(scope.names_at(p3)) == {'foo': 20}


def test_simple_if():
    source, p1, p2 = sp('''\
        a = 10
        if True:
            b = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'a': 10, 'b': 10}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'b': {10, 'undefined'}}


def test_if():
    source, p1, p2, p3, p4, p5 = sp('''\
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
    assert nvalues(scope.names_at(p1)) == {'a': 10, 'b': 10}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'b': 10, 'c': 10}
    assert nvalues(scope.names_at(p3)) == {'a': 30}
    assert nvalues(scope.names_at(p4)) == {'a': 30, 'b': 20}
    assert nvalues(scope.names_at(p5)) == {
        'a': {10, 30},
        'b': {10, 20, 'undefined'},
        'c': {10, 20, 'undefined'}
    }


def test_for_without_break():
    source, p1, p2, p3, p4 = sp('''\
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
    assert nvalues(scope.names_at(p1)) == {'a': 'listitem', 'b': {10, 20}}
    assert nvalues(scope.names_at(p2)) == {'a': 'listitem', 'b': 20}
    assert nvalues(scope.names_at(p3)) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}
    assert nvalues(scope.names_at(p4)) == {'a': {'listitem', 'undefined'}, 'b': {10, 20}, 'c': 10}


def test_for_with_inner_try():
    source, p1 = sp('''\
        for name in (1, 3):
            name(); |
            try:
                boo = 10
            except KeyError:
                pass
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'name': 'listitem', 'boo': {10, 'undefined'}}


def test_while_without_break():
    source, p1, p2, p3, p4 = sp('''\
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
    assert nvalues(scope.names_at(p1)) == {'b': {10, 20}}
    assert nvalues(scope.names_at(p2)) == {'b': 20}
    assert nvalues(scope.names_at(p3)) == {'b': {10, 20}, 'c': 10}
    assert nvalues(scope.names_at(p4)) == {'b': {10, 20}, 'c': 10}


def test_imports():
    source, = sp('''\
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
    source, p1, p2 = sp('''\
        import traceback;|
        a = 10;|
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'traceback': 'import:traceback'}
    assert nvalues(scope.names_at(p2)) == {'traceback': 'import:traceback', 'a': 10}


def test_simple_try_except():
    source, p1, p2 = sp('''\
        try:
            a = 10
        except:
            |a = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {}
    assert nvalues(scope.names_at(p2)) == {'a': {10, 20}}


def test_try_except():
    source, p1, p2, p3, p4, p5 = sp('''\
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
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'e': 'ValueError'}
    assert nvalues(scope.names_at(p2)) == {'a': 20, 'e': 'ValueError'}
    assert nvalues(scope.names_at(p3)) == {'b': 10, 'ee': 'Exception'}
    assert nvalues(scope.names_at(p4)) == {'a': 10, 'c': 10}
    assert nvalues(scope.names_at(p5)) == {
        'a': {10, 20, 'undefined'},
        'c': {10, 'undefined'},
        'b': {10, 'undefined'},
        'e': {'ValueError', 'undefined'},
        'ee': {'Exception', 'undefined'},
    }


def test_function_scope():
    source, p1, p2 = sp('''\
        a = 10
        def foo(b):
            c = 10
            |
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'a': 10, 'b': 'foo.arg', 'c': 10, 'foo': 'func'}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'foo': 'func'}


def test_parent_scope_var_masking():
    source, p1, p2 = sp('''\
        a = 10
        def foo():
            |a = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'foo': 'func'}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'foo': 'func'}


def test_class_scope():
    source, p1, p2, p3, p4 = sp('''\
        a = 10
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
    assert nvalues(scope.names_at(p1)) == {'a': 10, 'Boo': 'class', 'BOO': 10}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'Boo': 'class', 'self': 'boo.arg', 'b': 10}
    assert nvalues(scope.names_at(p3)) == {'a': 10, 'Boo': 'class', 'boo': 'func', 'BOO': 10}
    assert nvalues(scope.names_at(p4)) == {'a': 10, 'Boo': 'class'}


def test_class_scope_reassign():
    source, p1, p2 = sp('''\
        boo = 10
        class Boo:
            boo = |boo
            |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'Boo': 'class', 'boo': 10}
    assert nvalues(scope.names_at(p2)) == {'Boo': 'class', 'boo': 'boo'}


def test_attr_assign():
    source, = sp('''\
        foo.boo = 10
    ''')
    create_scope(source)


def test_multiple_targest():
    source, = sp('''\
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
    assert set(scope.names_at(p)) == set(('boo', 'foo'))


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
    assert nvalues(scope.names_at(p)) == {
        'a': {10, 20},
        'b': 20,
        'boo': 'func',
        'foo': 'func'
    }


def test_one_line_scopes():
    source, p1, p2 = sp('''\
        def foo(): pass
        def boo(baz): return |10
        class bar: pass
        |
    ''')
    scope = create_scope(source)
    assert set(scope.names_at(p1)) == {'foo', 'boo', 'bar', 'baz'}
    assert set(scope.names_at(p2)) == {'foo', 'boo', 'bar'}


def test_multiline_expression():
    source, p = sp('''\
        foo = 10
        (foo +
             |boo)
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'foo': 10}


def test_multiline_expression2():
    source, p = sp('''\
        def foo(arg):
            return 'ArgumentName({}, {}, {})'.format(
                arg.name, |arg.location, arg.declared_at)
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'arg': 'foo.arg', 'foo': 'func'}


def test_lambda():
    source, p = sp('''\
        a = 10
        f = lambda b: a + |a
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {
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
    assert nvalues(scope.names_at(p)) == {'arg': 'foo.arg', 'foo': 'func', 'boo': 'func'}


def test_vargs():
    source, p = sp('''\
        def boo(*vargs):
            |pass
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'vargs': 'boo.arg', 'boo': 'func'}


def test_kwargs():
    source, p = sp('''\
        def boo(**kwargs):
            |pass
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'kwargs': 'boo.arg', 'boo': 'func'}


def test_list_comprehension():
    source, p1, p2 = sp('''\
        [|r for |r in (1, 2, 3)]
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'r': 'listitem'}
    assert nvalues(scope.names_at(p2)) == {}


def test_generator_comprehension():
    source, p = sp('''\
        (|r for r in (1, 2, 3))
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'r': 'listitem'}


def test_dict_comprehension():
    source, p = sp('''\
        {1: |r for r in (1, 2, 3)}
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'r': 'listitem'}


def test_set_comprehension():
    source, p = sp('''\
        {|r for r in (1, 2, 3)}
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'r': 'listitem'}


def test_with():
    source, p = sp('''\
        with open('boo') as f:
            |pass
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'f': 'with'}


def test_multi_assign():
    source, p = sp('''\
        a = b = 10
        |
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'a': 10, 'b': 10}


def test_visit_value_node_in_unsupported_assignments():
    source, p = sp('''\
        foo.boo = lambda a: |a + 1
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'a': 'lambda.arg'}


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
    assert nvalues(scope.names_at(p)) == {'e': 'Exception'}


def test_global():
    source, p1, p2 = sp('''\
        def foo():
            global boo
            boo = 10

        def bar():
            |pass
        |
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'foo': 'func', 'bar': 'func', 'boo': 10}
    assert nvalues(scope.names_at(p2)) == {'foo': 'func', 'bar': 'func'}


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
    assert nvalues(scope.names_at(p)) == {'boo': 'listitem'}


def test_nested_nest():
    source, p1, p2, p3, p4 = sp('''\
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
    assert nvalues(scope.names_at(p4)) == {'a': 10, 'b': 10, 'c': 10}
    assert nvalues(scope.names_at(p3)) == {'a': 10, 'b': 10, 'c': {10, 'undefined'}}
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}
    assert nvalues(scope.names_at(p1)) == {'a': {10, 'undefined'},
                                           'b': {10, 'undefined'},
                                           'c': {10, 'undefined'}}


def test_scope_shift_after_nested_flow():
    source, p = sp('''\
        if True:
            if True:
                pass

        boo = 10
        return |boo
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'boo': 10}


def test_names_at_flow_start():
    source, p = sp('''\
        def foo(boo):
            with |boo:
                pass
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'boo': 'foo.arg', 'foo': 'func'}


def test_lambda_in_gen_expression():
    source, p = sp('''\
        [i for i in filter(lambda r: |r, [1,2,3])]
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'r': 'lambda.arg'}


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
    assert nvalues(scope.names_at(p)) == {'boo': 10}


def test_multi_comprehensions():
    source, p1, p2, p3 = sp('''\
        [x for x in [] for y in |x if |y if |x]
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'x': 'listitem'}
    assert nvalues(scope.names_at(p2)) == {'x': 'listitem', 'y': 'x'}
    assert nvalues(scope.names_at(p3)) == {'x': 'listitem', 'y': 'x'}


def test_nested_comprehensions():
    source, p1, p2 = sp('''\
        [[|r for r in |x] for x in []]
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'x': 'listitem', 'r': 'x'}
    assert nvalues(scope.names_at(p2)) == {'x': 'listitem'}


def test_visit_decorator():
    source, p = sp('''\
        @boo(|r for r in [])
        def foo():
            pass
    ''')
    scope = create_scope(source)
    assert nvalues(scope.names_at(p)) == {'r': 'listitem', 'foo': 'func'}


def test_flow_position_shoud_ignore_fake_flows():
    source, p1, p2 = sp('''\
        def foo(source):
            |source = [r for r in source.splitlines()]
            source = 'very long text to catch   region'.format(|source)
    ''')
    scope = create_scope(source)
    result = scope.names_at(p2)
    assert result['source'].declared_at == p1


def test_nested_expression_regions():
    source, p = sp('''\
        {r.id: (
            r.related_artists and list(r.related_artists) or [],
            |r.image_orig_width,
        ) for r in []}
    ''')
    scope = create_scope(source)
    result = scope.names_at(p)
    assert nvalues(result) == {'r': 'listitem'}


def test_import_name_locations():
    source, = sp('''\
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
    names = scope.names_at(p)
    assert type(names['foo']) == AssignedName


def test_dotted_imports():
    source, p = sp('''\
        import os.path
        |
    ''')
    scope = create_scope(source)
    names = scope.names_at(p)
    assert nvalues(names) == {'os': 'import:os'}


def test_star_imports():
    source, p = sp('''\
        from os.path import *
        |
    ''')

    scope = create_scope(source)
    scope.resolve_star_imports(Project())
    names = scope.names_at(p)
    assert 'join' in names
    assert 'abspath' in names


# def test_boo():
#     scope = create_scope(open('/usr/lib/python2.7/posixpath.py').read())
#     print scope.flows[0]
#     assert False
