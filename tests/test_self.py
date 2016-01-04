import os
from itertools import chain

from supp import linter
from supp.util import Source
from supp.astwalk import Extractor
from supp.compat import PY2


def pytest_generate_tests(metafunc):
    if 'fname' in metafunc.funcargnames:
        fnames = []
        for top, dirs, files in chain(os.walk('supp'), os.walk('tests')):
            for fname in files:
                if fname.endswith('.py'):
                    fnames.append(os.path.join(top, fname))
        metafunc.parametrize('fname', fnames)


def test_scope(fname):
    source = Source(open(fname).read(), fname)
    scope = Extractor(source).process()


def test_lint(fname):
    result = linter.lint(None, open(fname).read(), fname)
    for r in result:
        error, description = r[:2]
        if error[0] == 'E':
            if (not PY2 and error == 'E02' and
                    (' unicode' in description or ' long' in description)):
                continue

            assert False, '{}: {}'.format(fname, r)
