from supp.assistant import usages
from supp.project import Project

from .helpers import sp


def tusages(source, project=None, filename=None):
    return usages(project or Project(), source, filename)


def test_simple():
    source, _p = sp('''\
        s = 'boo'
        while s:
            foo(s)
    ''')

    tusages(source)
    # assert False
