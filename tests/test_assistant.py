from supp.assistant import assist
from supp.project import Project

from .helpers import sp


def tassist(source, pos, project=None, filename=None):
    return assist(project or Project(), source, pos, filename)


def test_simple_from():
    source, p = sp('''\
        from mul|
    ''')

    m, result = tassist(source, p)
    assert m == 'mul'
    assert 'multiprocessing' in result

    starts_with_mul = all(r.startswith('mul') for r in result)
    assert starts_with_mul


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

    starts_with_mul = all(r.startswith('mul') for r in result)
    assert starts_with_mul


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
    assert 'boo' not in result


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
