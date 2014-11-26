import pytest
from supp.util import print_dump
from supp.project import Project

__builtins__['pytest'] = pytest
__builtins__['print_dump'] = print_dump


@pytest.fixture
def project(tmpdir):
    project = Project(str(tmpdir))
    def add_module(name, content=None, lazy=False):
        parts = name.split('.')
        module = parts[-1]
        pkg = parts[:-1]
        root = tmpdir
        for p in pkg:
            root = root.join(p)
            if not lazy:
                root.join('__init__.py').ensure()

        m = root.join(module + '.py')
        if not lazy:
            if content:
                m.write(content)
            else:
                m.ensure()

        return str(m)

    project.add_module = add_module
    project.get_module = lambda name: add_module(name, lazy=True)
    return project
