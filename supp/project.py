import os
import sys
import imp

from .compat import range, reduce

suffixes = [s for s, _, _ in imp.get_suffixes()]

class Project(object):
    def __init__(self, src=None):
        self.src = src or '.'

    def list_packages(self, root, filename=None):
        modules = set()
        path = sys.path + [self.src]

        if root.startswith('.'):
            path = [reduce(
                lambda p, _: os.path.dirname(p),
                range(len(root) - len(root.rstrip('.'))),
                filename
            )]
        else:
            if root:
                droot = root + '.'
                for package in sys.modules:
                    if package.startswith(droot):
                        modules.add(package[len(droot):].partition('.')[0])
            else:
                for package in sys.modules:
                    modules.add(package.partition('.')[0])

        for p in path:
            pdir = os.path.join(p, *root.split('.'))
            try:
                dlist = os.listdir(pdir)
            except OSError:
                continue

            for name in dlist:
                for s in suffixes:
                    if name.endswith(s):
                        mname = name[:-len(s)]
                        if mname == '__init__': continue
                        modules.add(mname)
                        break
                else:
                    if os.path.exists(os.path.join(p, name, '__init__.py')):
                        modules.add(name)

        return modules
