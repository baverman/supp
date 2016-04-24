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

    def __repr__(self):
        return 'SourceModule({}, {})'.format(self.name, self.filename)

    @property
    def changed(self):
        return self.mtime != getmtime(self.filename)

    @cached_property
    def scope(self):
        e = Extractor(Source(open(self.filename).read(), self.filename))
        return e.process()

    @property
    def names(self):
        return self.scope.exported_names


class ImportedName(object):
    def __init__(self, name, value):
        self.name = name
        self.value = value

    @property
    def names(self):
        return {k: ImportedName(k, v) for k, v in iteritems(vars(self.value))}


class ImportedModule(object):
    def __init__(self, module):
        self.module = module
        self.changed = False

    @property
    def names(self):
        return {k: ImportedName(k, v) for k, v in iteritems(vars(self.module))}
