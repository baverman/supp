from __future__ import print_function

from supp.compat import iteritems
from supp.scope import create_scope
from supp.astwalk import AssignedName, UndefinedName, MultiName

from .helpers import sp

undefined = object()


def get_value(name):
    if isinstance(name, AssignedName):
        return name.value_node.n
    elif isinstance(name, UndefinedName):
        return undefined
    elif isinstance(name, MultiName):
        return set(get_value(r) for r in name.names)
    else:
        raise Exception('Unknown name type', name)


def nvalues(names):
    return {k: get_value(v) for k, v in iteritems(names)}


def test_global_scope():
    source, p1, p2 = sp('''\
        foo = 10
        |boo = 20
        |
    ''')

    scope = create_scope(source)
    assert nvalues(scope.names) == {'foo': 10, 'boo': 20}
    assert nvalues(scope.names_at(p1)) == {'foo': 10}
    assert nvalues(scope.names_at(p2)) == {'foo': 10, 'boo': 20}


def test_if_in_global_scope():
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
    assert nvalues(scope.names_at(p5)) == {'a': {10, 30}, 'b': {10, 20, undefined}, 'c': {10, 20, undefined}}
