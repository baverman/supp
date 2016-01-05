from textwrap import dedent

import pytest
from supp.project import Project


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
                m.write(dedent(content))
            else:
                m.ensure()

        return str(m)

    project.add_m = add_module
    project.get_m = lambda name: add_module(name, lazy=True)
    return project
