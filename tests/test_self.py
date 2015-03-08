import os

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


def test_scope(fname):
    source = Source(open(fname).read(), fname)
    scope = Extractor(source).process()
