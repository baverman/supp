from supp.assistant import assist
from supp.project import Project

from .helpers import sp


def tassist(source, pos, project=None, filename=None):
    return assist(project or Project(), source, pos, filename)


def test_simple_from():
    source, p = sp('''\
        from mul|
    ''')

    result = tassist(source, p)
    assert 'multiprocessing' in result

    starts_with_mul = all(r.startswith('mul') for r in result)
    assert starts_with_mul


def test_from_all():
    source, p = sp('''\
        from |
    ''')
    result = tassist(source, p)
    assert 'os' in result
    assert 'sys' in result


def test_from_with_parent_package():
    source, p = sp('''\
        from multiprocessing.|
    ''')

    result = tassist(source, p)
    assert 'connection' in result
    assert 'process' in result


def test_dyn_from_with_parent_package():
    source, p = sp('''\
        from os.|
    ''')

    result = tassist(source, p)
    assert 'path' in result


def test_from_src(project):
    project.add_module('testp.module')
    source, p = sp('''\
        from testp.|
    ''')
    result = tassist(source, p, project)
    assert result == ['module']


def test_relative_from(project):
    project.add_module('testp.module')
    source, p = sp('''\
        from .|
    ''')
    result = tassist(source, p, project, project.get_module('testp.tmodule'))
    assert 'module' in result

    source, p = sp('''\
        from ..|
    ''')
    result = tassist(source, p, project, project.get_module('testp.pkg.tmodule'))
    assert 'module' in result


def test_simple_import():
    source, p = sp('''\
        import mul|
    ''')
    result = tassist(source, p)
    assert 'multiprocessing' in result

    starts_with_mul = all(r.startswith('mul') for r in result)
    assert starts_with_mul


def test_comma_import():
    source, p = sp('''\
        import os, mul|
    ''')
    result = tassist(source, p)
    assert 'multiprocessing' in result


def test_dotted_import():
    source, p = sp('''\
        import os.|
    ''')
    result = tassist(source, p)
    assert 'path' in result


def test_import_all():
    source, p = sp('''\
        import |
    ''')
    result = tassist(source, p)
    assert 'os' in result
    assert 'sys' in result


def test_import_from_simple():
    source, p = sp('''\
        from multiprocessing import |
    ''')
    result = tassist(source, p)
    assert 'connection' in result
    assert 'pool' in result


def test_import_from_simple(project):
    project.add_module('testp.module')
    source, p = sp('''\
        from . import |
    ''')
    result = tassist(source, p, project, project.get_module('testp.tmodule'))
    assert 'module' in result
