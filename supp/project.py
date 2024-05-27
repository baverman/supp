import os
import sys

from contextlib import contextmanager

from .compat import range
from .module import SourceModule, ImportedModule

try:
    import importlib.machinery
    SUFFIXES = importlib.machinery.all_suffixes()
except:
    import imp  # type: ignore[import-not-found]
    SUFFIXES = [s for s, _, _ in imp.get_suffixes()]

SOURCE_SUFFIXES = ('.py',)

if False:
    import typing as t
    from .name import Object


class Project(object):
    def __init__(self, sources=None, dyn_modules=None):
        # type: (list[str] | None, list[str] | None) -> None
        self.sources = sources or ['.']
        self._norm_cache = {}  # type: dict[str, list[str]]
        self._module_cache = {}  # type: dict[str, ImportedModule | SourceModule]
        self._context_cache = {}  # type: dict[str, ImportedModule | SourceModule]
        self.dyn_modules = set(dyn_modules or [])

    def get_path(self):
        # type: () -> list[str]
        return  self.sources + sys.path

    def list_packages(self, root):
        # type: (str) ->  set[str]
        modules = set()
        path = self.get_path()

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
                for s in SUFFIXES:
                    if name.endswith(s):
                        mname = name[:-len(s)]
                        if mname == '__init__':
                            continue
                        modules.add(mname)
                        break
                else:
                    if os.path.exists(os.path.join(pdir, name, '__init__.py')):
                        modules.add(name)

        return modules

    @contextmanager
    def check_changes(self):
        # type: () -> t.Iterator[None]
        self._context_cache.clear()
        yield

    def get_nmodule(self, name, filename):
        # type: (str, str) -> SourceModule | ImportedModule
        return self.get_module(self.norm_package(name, filename))

    def get_module(self, name):
        # type: (str) -> SourceModule | ImportedModule
        try:
            return self._context_cache[name]
        except KeyError:
            pass

        try:
            m = self._module_cache[name]
            if m.changed:
                del self._module_cache[name]
            else:
                self._context_cache[name] = m
                return m
        except KeyError:
            pass

        path = self.get_path()
        filename = None
        is_source = False
        for p in path:
            mpath = os.path.join(p, *name.split('.'))
            for s in SUFFIXES:
                fname = mpath + s
                if os.path.exists(fname):
                    filename = fname
                    is_source = s in SOURCE_SUFFIXES
                    break
            else:
                fname = os.path.join(mpath, '__init__.py')
                if os.path.exists(fname):
                    filename = fname
                    is_source = True
                    break

            if filename:
                break

        module = None  # type: SourceModule | ImportedModule | None
        if not filename:
            if name in sys.modules:
                module = ImportedModule(sys.modules[name])
        else:
            if name in self.dyn_modules or not is_source:
                if name not in sys.modules:
                    __import__(name)
                module = ImportedModule(sys.modules[name])
            else:
                module = SourceModule(self, name, filename)

        if not module:
            raise ImportError(name)

        self._module_cache[name] = module
        return module

    def norm_package(self, package, filename):
        # type: (str, str) -> str
        if not package.startswith('.'):
            return package

        root = filename
        for _ in range(len(package) - len(package.lstrip('.'))):
            root = os.path.dirname(root)

        key = root
        try:
            parts = self._norm_cache[key]
        except KeyError:
            parts = []
            while True:
                if os.path.exists(os.path.join(root, '__init__.py')):
                    parts.insert(0, os.path.basename(root))
                    root = os.path.dirname(root)
                else:
                    break

            if not parts:
                raise Exception('Not a package: {} ({})'.format(filename, package))

            self._norm_cache[key] = parts

        package = package.lstrip('.')
        if package:
            parts = parts + [package]
        return '.'.join(parts)
