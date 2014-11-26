from supp.compat import iteritems
from supp.astwalk import AssignedName, UndefinedName, MultiName, ImportedName,\
    Extractor, ArgumentName, FuncScope, ClassScope
from supp.util import Source, print_dump

from .helpers import sp


def create_scope(source, filename=None, debug=False):
    e = Extractor(Source(source, filename))
    debug and print_dump(e.tree)
    return e.process()


def get_value(name):
    if isinstance(name, AssignedName):
        if hasattr(name.value_node, 'elts'):
            return 'listitem'
        if hasattr(name.value_node, 'id'):
            return name.value_node.id
        return name.value_node.n
    elif isinstance(name, UndefinedName):
        return 'undefined'
    elif isinstance(name, MultiName):
        return set(get_value(r) for r in name.names)
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
    source, p1, p2 = sp('''\
        foo = 10
        foo = |20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 20}
    assert nvalues(scope.names_at(p1)) == {'foo': 10}
    assert nvalues(scope.names_at(p2)) == {'foo': 20}


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
