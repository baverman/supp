import os

from supp import linter
from supp.util import Source
from supp.astwalk import Extractor


def pytest_generate_tests(metafunc):
    if 'fname' in metafunc.funcargnames:
        fnames = []
        for top, dirs, files in os.walk('supp'):
            for fname in files:
                if fname.endswith('.py'):
                    fnames.append(os.path.join(top, fname))
        metafunc.parametrize('fname', fnames)


def _test_scope(fname):
    source = Source(open(fname).read(), fname)
    scope = Extractor(source).process()


def test_lint(fname):
    result = linter.lint(None, open(fname).read(), fname)
    # print result
    # assert False
