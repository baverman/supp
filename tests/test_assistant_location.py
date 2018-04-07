import os
from supp.assistant import location, _loc
from supp.project import Project

from .helpers import sp


def tlocation(source, pos, project=None, filename=None, debug=False):
    debug = debug or os.environ.get('DEBUG')
    return location(project or Project(), source, pos, filename, debug=debug)


def test_instance_attributes_locations():
    source, p = sp('''\
        class Boo(Bar):
            def baz(self):
                self.bar = 10

            def foo(self):
                self.bar = 20

            def boo(self):
                self.b|ar = 30
    ''')

    result = tlocation(source, p[0])
    assert result == [[{'loc': (3, 8), 'file': '<string>'},
                       {'loc': (6, 8), 'file': '<string>'}]]


def test_module_name_location():
    source, p = sp('''\
        def foo(): pass
        boo = 10
        f|oo
        |boo
    ''')

    loc, = tlocation(source, p[0])
    assert loc['loc'] == (1, 4)

    loc, = tlocation(source, p[1])
    assert loc['loc'] == (2, 0)


def test_imported_name_location(project):
    project.add_m('testp.testm', '''\
        boo = 20
    ''')

    source, p = sp('''\
        import testp.te|stm
        from testp.testm import b|oo
        bo|o
        from . import tes|tm
    ''')

    loc, = tlocation(source, p[0], project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (1, 0)
    assert loc['file'] == project.get_m('testp.testm')

    loc, = tlocation(source, p[1], project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (1, 0)
    assert loc['file'] == project.get_m('testp.testm')

    locs = tlocation(source, p[2], project, filename=project.get_m('testp.testm2'))
    assert locs == [_loc((2, 24), project.get_m('testp.testm2')),
                    _loc((1, 0), project.get_m('testp.testm'))]

    locs = tlocation(source, p[3], project, filename=project.get_m('testp.testm2'))
    assert locs == [_loc((1, 0), project.get_m('testp.testm'))]


def test_imported_attr_location(project):
    project.add_m('testp.testm', '''\
        bar = 10

        def boo():
            pass

        foo = boo
    ''')

    source, p = sp('''\
        import testp.testm
        from testp import testm
        from testp import testm as am
        testm.bo|o
        am.bo|o
        testm.fo|o
        testp.tes|tm.boo
        from testp.tes|tm.boo import foo
    ''')

    loc, = tlocation(source, p[0], project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (3, 4)
    assert loc['file'] == project.get_m('testp.testm')

    loc, = tlocation(source, p[1], project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (3, 4)
    assert loc['file'] == project.get_m('testp.testm')

    locs = tlocation(source, p[2], project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((6, 0), project.get_m('testp.testm')),
    ]

    locs = tlocation(source, p[3], project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((0, 0), project.get_m('testp.testm2')),
        _loc((1, 0), project.get_m('testp.testm')),
    ]

    locs = tlocation(source, p[4], project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((1, 0), project.get_m('testp.testm')),
    ]


# def test_boo():
#     project = Project(['/home/bobrov/work/supp'])
#     source = open(__file__.rstrip('c')).read()
#     loc, fname = tlocation(source, (4, 23), project, filename=__file__)
#     print loc, fname
#     assert False
