from os.path import getmtime

from .util import cached_property, Source
from .astwalk import Extractor
from .compat import iteritems


class SourceModule(object):
    def __init__(self, name, project, filename):
        self.project = project
        self.name = name
        self.filename = filename
        self.mtime = getmtime(filename)
        self.declared_at = 1, 0

    def __repr__(self):
        return 'SourceModule({}, {})'.format(self.name, self.filename)

    @property
    def changed(self):
        return self.mtime != getmtime(self.filename)

    @cached_property
    def scope(self):
        e = Extractor(Source(open(self.filename).read(), self.filename))
        scope = e.process()
        scope.resolve_star_imports(self.project)
        return scope

    @property
    def names(self):
        return self.scope.exported_names


class ImportedName(object):
    def __init__(self, name, value):
        self.name = name
        self.value = value

    @cached_property
    def names(self):
        try:
            return {k: ImportedName(k, v) for k, v in iteritems(vars(self.value))}
        except TypeError:
            return {k: ImportedName(k, getattr(self.value, k, None)) for k in dir(self.value)}


class ImportedModule(object):
    def __init__(self, module):
        self.module = module
        self.changed = False

    @cached_property
    def names(self):
        return {k: ImportedName(k, v) for k, v in iteritems(vars(self.module))}
