from supp.assistant import assist, location, _loc
from supp.project import Project

from .helpers import sp


def tassist(source, pos, project=None, filename=None, debug=False):
    return assist(project or Project(), source, pos, filename, debug=debug)


def tlocation(source, pos, project=None, filename=None, debug=False):
    return location(project or Project(), source, pos, filename, debug=debug)


def test_simple_from():
    source, p = sp('''\
        from mul|
    ''')

    m, result = tassist(source, p)
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_from_all():
    source, p = sp('''\
        from |
    ''')
    m, result = tassist(source, p)
    assert m == ''
    assert 'os' in result
    assert 'sys' in result


def test_from_with_parent_package():
    source, p = sp('''\
        from multiprocessing.|
    ''')

    m, result = tassist(source, p)
    assert m == ''
    assert 'connection' in result
    assert 'process' in result


def test_dyn_from_with_parent_package():
    source, p = sp('''\
        from os.|
    ''')

    m, result = tassist(source, p)
    assert m == ''
    assert 'path' in result


def test_from_src(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from testp.|
    ''')
    m, result = tassist(source, p, project)
    assert m == ''
    assert result == ['module']


def test_relative_from(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from .|
    ''')
    m, result = tassist(source, p, project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result

    source, p = sp('''\
        from ..|
    ''')
    m, result = tassist(source, p, project, project.get_m('testp.pkg.tmodule'))
    assert m == ''
    assert 'module' in result


def test_simple_import():
    source, p = sp('''\
        import mul|
    ''')
    m, result = tassist(source, p)
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_comma_import():
    source, p = sp('''\
        import os, mul|
    ''')
    m, result = tassist(source, p)
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_dotted_import():
    source, p = sp('''\
        import os.|
    ''')
    m, result = tassist(source, p)
    assert m == ''
    assert 'path' in result


def test_import_all():
    source, p = sp('''\
        import |
    ''')
    m, result = tassist(source, p)
    assert m == ''
    assert 'os' in result
    assert 'sys' in result


def test_import_from_simple1():
    source, p = sp('''\
        from multiprocessing import |
    ''')
    m, result = tassist(source, p)
    assert m == ''
    assert 'connection' in result
    assert 'pool' in result
    assert 'Exception' not in result


def test_import_from_simple2(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from . import |
    ''')
    m, result = tassist(source, p, project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result


def test_import_from_simple3(project):
    project.add_m('testp.module.submod')
    source, p = sp('''\
        from .module import |
    ''')
    m, result = tassist(source, p, project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'submod' in result


def test_import_from_module_names(project):
    project.add_m('testp.__init__', '''\
        foo = 10
    ''')
    project.add_m('testp.module')

    source, p = sp('''\
        from testp import |
    ''')
    m, result = tassist(source, p, project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result
    assert 'foo' in result

    # test changed module cache
    m, result = tassist(source, p, project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result
    assert 'foo' in result


def test_name_assist():
    source, p = sp('''\
        boo = 10
        foo = 20
        f|
    ''')
    m, result = tassist(source, p)
    assert m == 'f'
    assert 'foo' in result
    assert 'boo' in result


def test_dynamic_modules():
    project = Project()
    source, p = sp('''\
        from os.path import j|
    ''')

    m, result = tassist(source, p, project)
    assert m == 'j'
    assert 'join' in result

    # test changed module cache
    m, result = tassist(source, p, project)
    assert m == 'j'
    assert 'join' in result


# def test_imported_name_attributes():
#     project = Project()
#     source, p = sp('''\
#         from multiprocessing.connection import Client
#         path.j|
#     ''')
#     m, result = tassist(source, p, project)
#     assert m == 'j'
#     assert 'join' in result


def test_imported_name_modules():
    project = Project()
    source, p = sp('''\
        from multiprocessing import connection
        connection.Cl|
    ''')
    m, result = tassist(source, p, project)
    assert m == 'Cl'
    assert 'Client' in result


def test_module_name_location():
    source, p1, p2 = sp('''\
        def foo(): pass
        boo = 10
        f|oo
        |boo
    ''')

    loc, = tlocation(source, p1)
    assert loc['loc'] == (1, 4)

    loc, = tlocation(source, p2)
    assert loc['loc'] == (2, 0)


def test_imported_name_location(project):
    project.add_m('testp.testm', '''\
        boo = 20
    ''')

    source, p1, p2, p3, p4 = sp('''\
        import testp.te|stm
        from testp.testm import b|oo
        bo|o
        from . import tes|tm
    ''')

    loc, = tlocation(source, p1, project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (1, 0)
    assert loc['file'] == project.get_m('testp.testm')

    loc, = tlocation(source, p2, project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (1, 0)
    assert loc['file'] == project.get_m('testp.testm')

    locs = tlocation(source, p3, project, filename=project.get_m('testp.testm2'))
    assert locs == [_loc((2, 24), project.get_m('testp.testm2')),
                    _loc((1, 0), project.get_m('testp.testm'))]

    locs = tlocation(source, p4, project, filename=project.get_m('testp.testm2'))
    assert locs == [_loc((1, 0), project.get_m('testp.testm'))]


def test_imported_attr_location(project):
    project.add_m('testp.testm', '''\
        bar = 10

        def boo():
            pass

        foo = boo
    ''')

    source, p1, p2, p3, p4, p5 = sp('''\
        import testp.testm
        from testp import testm
        from testp import testm as am
        testm.bo|o
        am.bo|o
        testm.fo|o
        testp.tes|tm.boo
        from testp.tes|tm.boo import foo
    ''')

    loc, = tlocation(source, p1, project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (3, 4)
    assert loc['file'] == project.get_m('testp.testm')

    loc, = tlocation(source, p2, project, filename=project.get_m('testp.testm2'))
    assert loc['loc'] == (3, 4)
    assert loc['file'] == project.get_m('testp.testm')

    locs = tlocation(source, p3, project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((6, 0), project.get_m('testp.testm')),
    ]

    locs = tlocation(source, p4, project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((0, 0), project.get_m('testp.testm2')),
        _loc((1, 0), project.get_m('testp.testm')),
    ]

    locs = tlocation(source, p5, project, filename=project.get_m('testp.testm2'))
    assert locs == [
        _loc((1, 0), project.get_m('testp.testm')),
    ]


def test_recursive_imported_name(project):
    project.add_m('testp.testm', '''\
        import datetime
    ''')

    source, p = sp('''\
        from testp.testm import datetime
        datetime.|
    ''')

    _, result = tassist(source, p, project)
    assert 'timedelta' in result


def test_assigned_imported_name():
    source, p = sp('''\
        from multiprocessing import connection
        cn = connection
        cn.|
    ''')
    _, result = tassist(source, p)
    assert 'Client' in result


def test_deep_attribute():
    source, p = sp('''\
        import os.path
        os.path.|
    ''')
    _, result = tassist(source, p)
    assert 'join' in result


def test_import_space():
    source, p = sp('''\
        import multiprocessing.connection
        multiprocessing.connection.|
    ''')
    _, result = tassist(source, p)
    assert 'Client' in result


def test_class_attribute():
    source, p = sp('''\
        class Foo(object):
            def foo(self):
                pass

        class Bar:
            def bar(self):
                pass

        class Boo(Foo, Bar):
            def boo(self):
                pass

        Boo.|
    ''')
    _, result = tassist(source, p)
    assert 'boo' in result
    assert 'foo' in result
    assert 'bar' in result
    assert '__doc__' in result


def test_instance_attribute():
    source, p = sp('''\
        class Boo(object):
            def boo(self):
                pass

        bar = Boo()
        bar.|
    ''')
    _, result = tassist(source, p)
    assert 'boo' in result


def test_basic_self():
    source, p = sp('''\
        class Boo(object):
            def boo(self):
                self.|
    ''')

    _, result = tassist(source, p)
    assert 'boo' in result


def test_instance_attributes():
    source, p = sp('''\
        class Bar(object):
            def foobar(self):
                pass

        class Boo(object):
            def foo(self):
                self.bar = Bar()

            def boo(self):
                self.bar.|
    ''')

    _, result = tassist(source, p)
    assert 'foobar' in result


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

    result = tlocation(source, p)
    assert result == [[{'loc': (3, 8), 'file': '<string>'},
                       {'loc': (6, 8), 'file': '<string>'}]]


def test_inherited_instance_attributes():
    source, p = sp('''\
        class Bar(object):
            def __init__(self):
                self.foobar = 10

        class Foo(object):
            def foo(self):
                self.bar = Bar()

        class Boo(Foo):
            def boo(self):
                self.bar.|
    ''')

    _, result = tassist(source, p)
    assert 'foobar' in result


def test_func_call_result():
    source, p = sp('''\
        def foo():
            return ""

        foo().|
    ''')

    _, result = tassist(source, p)
    assert 'startswith' in result


def _test_func_call_arg_result():
    source, p = sp('''\
        def foo(arg):
            return arg

        foo("").|
    ''')

    _, result = tassist(source, p, debug=True)
    assert 'startswith' in result


# def test_classmethod():
#     source, p = sp('''\
#         class Bar(object):
#             @classmethod
#             def bar(cls):
#                 return cls
#
#             def foo(self):
#                 pass
#
#         Bar.bar().|
#     ''')
#
#     _, result = tassist(source, p)
#     assert 'foo' in result


# def test_boo():
#     project = Project(['/home/bobrov/work/supp'])
#     source = open(__file__.rstrip('c')).read()
#     loc, fname = tlocation(source, (4, 23), project, filename=__file__)
#     print loc, fname
#     assert False


# def test_boo():
#     root = '/home/bobrov/zvooq/zvq-prod'
#     project = Project([root])
#     source = open(root + '/zvooq/db/__init__.py').read()
#     locs = tlocation(source, (133, 18), project, filename=__file__)
#     print locs
#     assert False
