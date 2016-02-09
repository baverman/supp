from supp.assistant import assist, location
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

    loc, _ = tlocation(source, p1)
    assert loc == (1, 0)

    loc, _ = tlocation(source, p2)
    assert loc == (2, 0)


def test_imported_name_location(project):
    project.add_m('testp.testm', '''\
        boo = 20
    ''')

    source, p = sp('''\
        from testp.testm import boo
        bo|o
    ''')

    loc, fname = tlocation(source, p, project, filename=project.get_m('testp.testm2'))
    assert loc == (1, 0)
    assert fname == project.get_m('testp.testm')


def test_imported_attr_location(project):
    project.add_m('testp.testm', '''\
        def boo():
            pass
    ''')

    source, p1, p2 = sp('''\
        from testp import testm
        from testp import testm as am
        testm.bo|o
        am.bo|o
    ''')

    loc, fname = tlocation(source, p1, project, filename=project.get_m('testp.testm2'))
    assert loc == (1, 0)
    assert fname == project.get_m('testp.testm')

    loc, fname = tlocation(source, p2, project, filename=project.get_m('testp.testm2'))
    assert loc == (1, 0)
    assert fname == project.get_m('testp.testm')
