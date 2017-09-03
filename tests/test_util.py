from supp.util import unmark, SOURCE_MARK, get_marked_import, Source, split_pkg
from .helpers import sp


def mark(name):
    return name.replace('|', SOURCE_MARK)


def test_marks():
    assert unmark(mark('|boo')) == 'boo'
    assert unmark(mark('bo|o')) == 'boo'
    assert unmark(mark('boo|')) == 'boo'

    assert unmark(mark('foo.|boo')) == 'foo.boo'
    assert unmark(mark('foo.bo|o')) == 'foo.boo'
    assert unmark(mark('foo.boo|')) == 'foo.boo'

    assert unmark(mark('foo.|boo.bar')) == 'foo.boo'
    assert unmark(mark('foo.bo|o.bar')) == 'foo.boo'
    assert unmark(mark('foo.boo|.bar')) == 'foo.boo'


def tmarked_import(source, filename, pos):
    s = Source(source, filename, pos)
    return get_marked_import(s.tree)


def test_marked_import(project):
    project.add_m('testp.testm')

    source, p = sp('''\n
        import b|oo
        import boo.f|oo
        from boo import fo|o
        from b|oo import foo
        from . import bo|o
        from .foo import bo|o
        from .fo|o import boo
        from .| import foo
    ''')

    fn = project.get_m('testp.testm')
    assert tmarked_import(source, fn, p[0]) == ('boo', None)
    assert tmarked_import(source, fn, p[1]) == ('boo.foo', None)
    assert tmarked_import(source, fn, p[2]) == ('boo', 'foo')
    assert tmarked_import(source, fn, p[3]) == ('boo', None)
    assert tmarked_import(source, fn, p[4]) == ('.', 'boo')
    assert tmarked_import(source, fn, p[5]) == ('.foo', 'boo')
    assert tmarked_import(source, fn, p[6]) == ('.foo', None)
    assert tmarked_import(source, fn, p[7]) == ('.', None)

    source, p  = sp('''\n
        import os.|
    ''')
    assert tmarked_import(source, fn, p[0]) == ('os.', None)


def test_split_pkg():
    assert split_pkg('boo') == ('', 'boo')
    assert split_pkg('boo.foo') == ('boo', 'foo')
    assert split_pkg('.') == ('.', '')
    assert split_pkg('.foo') == ('.', 'foo')
    assert split_pkg('.foo.boo') == ('.foo', 'boo')
    assert split_pkg('..') == ('..', '')
    assert split_pkg('..foo') == ('..', 'foo')
    assert split_pkg('..foo.boo') == ('..foo', 'boo')
    assert split_pkg('os.') == ('os', '')
    assert split_pkg('.boo.') == ('.boo', '')
