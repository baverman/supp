from os.path import getmtime

from .util import cached_property, Source, safe_attribute_error
from .astwalk import extract_scope
from .compat import iteritems
from .name import RuntimeName


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
        source = Source(open(self.filename).read(), self.filename)
        scope = extract_scope(self.project, source)
        return scope

    @property
    @safe_attribute_error
    def attrs(self):
        return self.scope.exported_names


class ImportedModule(object):
    def __init__(self, module):
        self.module = module
        self.changed = False

    @cached_property
    @safe_attribute_error
    def attrs(self):
        return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.module))}
