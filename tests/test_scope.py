from __future__ import print_function

from .helpers import sp

from supp.scope import create_scope


def test_global_scope():
    source, p1, p2 = sp('''\
        foo = 10
        |boo = 20
        |
    ''')

    scope = create_scope(source)
    assert set(scope.names) == {'foo', 'boo'}
    assert set(scope.names_at(p1)) == {'foo'}
    assert set(scope.names_at(p2)) == {'foo', 'boo'}
