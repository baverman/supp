from os.path import getmtime

from .util import cached_property, Source
from .nast import extract_scope
from .compat import iteritems
from .name import RuntimeName, Object

if False:
    import typing as t
    from .name import Attributes, Name
    from .scope import SourceScope
    from .project import Project


class SourceModule(Object):
    def __init__(self, project, name, filename):
        # type: (Project, str, str) -> None
        self.project = project
        self.name = name
        self.filename = filename
        self.mtime = getmtime(filename)
        self.declared_at = 1, 0

    def __repr__(self):
        # type: () -> str
        return 'SourceModule({}, {})'.format(self.name, self.filename)

    @property
    def changed(self):
        # type: () -> bool
        return self.mtime != getmtime(self.filename)

    @cached_property
    def scope(self):
        # type: () -> SourceScope
        source = Source(open(self.filename).read(), self.filename)
        scope = extract_scope(source, self.project)
        return scope

    @property
    def _attrs(self):
        # type: () -> dict[str, Object | Name]
        return self.scope.exported_names  # type: ignore[return-value]


class ImportedModule(Object):
    def __init__(self, module):
        # type: (object) -> None
        self.module = module
        self.changed = False

    @cached_property
    def _attrs(self):
        # type: () -> Attributes
        return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.module))}
