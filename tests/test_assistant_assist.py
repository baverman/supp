import os
import pytest
from supp.assistant import assist
from supp.project import Project

from .helpers import sp


def tassist(source, pos, project=None, filename=None, debug=False):
    debug = debug or os.environ.get('DEBUG')
    return assist(project or Project(), source, pos, filename, debug=debug)


def test_simple_from():
    source, p = sp('''\
        from mul|
    ''')

    m, result = tassist(source, p[0])
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_from_all():
    source, p = sp('''\
        from |
    ''')
    m, result = tassist(source, p[0])
    assert m == ''
    assert 'os' in result
    assert 'sys' in result


def test_from_with_parent_package():
    source, p = sp('''\
        from multiprocessing.|
    ''')

    m, result = tassist(source, p[0])
    assert m == ''
    assert 'connection' in result
    assert 'process' in result


def test_dyn_from_with_parent_package():
    source, p = sp('''\
        from os.|
    ''')

    m, result = tassist(source, p[0])
    assert m == ''
    assert 'path' in result


def test_from_src(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from testp.|
    ''')
    m, result = tassist(source, p[0], project)
    assert m == ''
    assert result == ['module']


def test_relative_from(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from .|
    ''')
    m, result = tassist(source, p[0], project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result

    source, p = sp('''\
        from ..|
    ''')
    m, result = tassist(source, p[0], project, project.get_m('testp.pkg.tmodule'))
    assert m == ''
    assert 'module' in result


def test_simple_import():
    source, p = sp('''\
        import mul|
    ''')
    m, result = tassist(source, p[0])
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_comma_import():
    source, p = sp('''\
        import os, mul|
    ''')
    m, result = tassist(source, p[0])
    assert m == 'mul'
    assert 'multiprocessing' in result


def test_dotted_import():
    source, p = sp('''\
        import os.|
    ''')
    m, result = tassist(source, p[0])
    assert m == ''
    assert 'path' in result


def test_import_all():
    source, p = sp('''\
        import |
    ''')
    m, result = tassist(source, p[0])
    assert m == ''
    assert 'os' in result
    assert 'sys' in result


def test_import_from_simple1():
    source, p = sp('''\
        from multiprocessing import |
    ''')
    m, result = tassist(source, p[0])
    assert m == ''
    assert 'connection' in result
    assert 'pool' in result
    assert 'Exception' not in result


def test_import_from_simple2(project):
    project.add_m('testp.module')
    source, p = sp('''\
        from . import |
    ''')
    m, result = tassist(source, p[0], project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result


def test_import_from_simple3(project):
    project.add_m('testp.module.submod')
    source, p = sp('''\
        from .module import |
    ''')
    m, result = tassist(source, p[0], project, project.get_m('testp.tmodule'))
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
    m, result = tassist(source, p[0], project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result
    assert 'foo' in result

    # test changed module cache
    m, result = tassist(source, p[0], project, project.get_m('testp.tmodule'))
    assert m == ''
    assert 'module' in result
    assert 'foo' in result


def test_name_assist():
    source, p = sp('''\
        boo = 10
        foo = 20
        f|
    ''')
    m, result = tassist(source, p[0])
    assert m == 'f'
    assert 'foo' in result
    assert 'boo' in result


def test_dynamic_modules():
    project = Project()
    source, p = sp('''\
        from os.path import j|
    ''')

    m, result = tassist(source, p[0], project)
    assert m == 'j'
    assert 'join' in result

    # test changed module cache
    m, result = tassist(source, p[0], project)
    assert m == 'j'
    assert 'join' in result


def test_imported_name_modules():
    project = Project()
    source, p = sp('''\
        from multiprocessing import connection
        connection.Cl|
    ''')
    m, result = tassist(source, p[0], project)
    assert m == 'Cl'
    assert 'Client' in result


def test_recursive_imported_name(project):
    project.add_m('testp.testm', '''\
        import datetime
    ''')

    source, p = sp('''\
        from testp.testm import datetime
        datetime.|
    ''')

    _, result = tassist(source, p[0], project)
    assert 'timedelta' in result


def test_assigned_imported_name():
    source, p = sp('''\
        from multiprocessing import connection
        cn = connection
        cn.|
    ''')
    _, result = tassist(source, p[0])
    assert 'Client' in result


def test_deep_attribute():
    source, p = sp('''\
        import os.path
        os.path.|
    ''')
    _, result = tassist(source, p[0])
    assert 'join' in result


def test_import_space():
    source, p = sp('''\
        import multiprocessing.connection
        multiprocessing.connection.|
    ''')
    _, result = tassist(source, p[0])
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
    _, result = tassist(source, p[0])
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
    _, result = tassist(source, p[0])
    assert 'boo' in result


def test_basic_self():
    source, p = sp('''\
        class Boo(object):
            def boo(self):
                self.|
    ''')

    _, result = tassist(source, p[0])
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

    _, result = tassist(source, p[0])
    assert 'foobar' in result


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

    _, result = tassist(source, p[0])
    assert 'foobar' in result


def test_func_call_result():
    source, p = sp('''\
        def foo():
            return ""

        foo().|
    ''')

    _, result = tassist(source, p[0])
    assert 'startswith' in result


@pytest.mark.xfail
def test_func_call_arg_result():
    source, p = sp('''\
        def foo(arg):
            return arg

        foo("").|
    ''')

    _, result = tassist(source, p[0], debug=True)
    assert 'startswith' in result


def test_classmethod():
    source, p = sp('''\
        class Bar(object):
            @classmethod
            def bar(cls):
                cls.f|
                return cls

            def foo(self):
                pass

        Bar.bar().f|
    ''')

    _, result = tassist(source, p[0])
    assert 'foo' in result

    _, result = tassist(source, p[1])
    assert 'foo' in result


def test_in_call_brackets():
    source, p = sp('''\
        boo = 10
        foo(b|)
    ''')

    m, result = tassist(source, p[0])
    assert 'boo' in result
    assert m == 'b'


def test_property():
    source, p = sp('''\
        class Boo:
            @property
            def boo(self):
                return ''

        Boo().boo.s|
    ''')

    _, result = tassist(source, p[0])
    assert 'startswith' in result
