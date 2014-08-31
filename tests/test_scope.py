from __future__ import print_function

from supp.compat import iteritems
from supp.scope import create_scope
from supp.astwalk import AssignedName, UndefinedName, MultiName, ImportedName

from .helpers import sp

undefined = 'undefined'
listitem = 'listitem'
iname = 'iname'


def get_value(name):
    if isinstance(name, AssignedName):
        if hasattr(name.value_node, 'elts'):
            return listitem
        if hasattr(name.value_node, 'id'):
            return name.value_node.id
        return name.value_node.n
    elif isinstance(name, UndefinedName):
        return undefined
    elif isinstance(name, MultiName):
        return set(get_value(r) for r in name.names)
    elif isinstance(name, ImportedName):
        return iname
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
    assert nvalues(scope.names_at(p2)) == {'a': 10, 'b': {10, undefined}}


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
        'b': {10, 20, undefined},
        'c': {10, 20, undefined}
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
    assert nvalues(scope.names_at(p1)) == {'a': listitem, 'b': {10, 20}}
    assert nvalues(scope.names_at(p2)) == {'a': listitem, 'b': 20}
    assert nvalues(scope.names_at(p3)) == {'a': {listitem, undefined}, 'b': {10, 20}, 'c': 10}
    assert nvalues(scope.names_at(p4)) == {'a': {listitem, undefined}, 'b': {10, 20}, 'c': 10}


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
    names = scope.names

    assert set(names) == {
        'os', 'so', 'path', 'opath', 'ospath',
        'boo', 'foo', 'bar', 'tar'
    }

    assert names['os'].module == 'os'
    assert names['so'].module == 'os'
    assert names['ospath'].module == 'os.path'
    assert names['path'].module == 'os'
    assert names['path'].mname == 'path'
    assert names['opath'].module == 'os'
    assert names['opath'].mname == 'path'
    assert names['boo'].module == '.'
    assert names['boo'].mname == 'boo'
    assert names['foo'].module == '..'
    assert names['foo'].mname == 'foo'
    assert names['bar'].module == '.boo'
    assert names['bar'].mname == 'bar'
    assert names['tar'].module == '.boo'
    assert names['tar'].mname == 'tar'


def test_oneliners():
    source, p1, p2 = sp('''\
        import traceback;|
        a = 10;|
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names_at(p1)) == {'traceback': iname}
    assert nvalues(scope.names_at(p2)) == {'traceback': iname, 'a': 10}


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
        'a': {10, 20, undefined},
        'c': {10, undefined},
        'b': {10, undefined},
        'e': {'ValueError', undefined},
        'ee': {'Exception', undefined},
    }
