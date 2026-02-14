from __future__ import annotations
from os.path import getmtime
import typing as t

from .util import cached_property, Source
from .nast import extract_scope
from .compat import iteritems
from .name import RuntimeName, Object

if t.TYPE_CHECKING:
    from .name import Attributes, Name
    from .scope import SourceScope
    from .project import Project


class SourceModule(Object):
    def __init__(self, project: Project, name: str, filename: str) -> None:
        self.project = project
        self.name = name
        self.filename = filename
        self.mtime = getmtime(filename)
        self.declared_at = 1, 0

    def __repr__(self) -> str:
        return 'SourceModule({}, {})'.format(self.name, self.filename)

    @property
    def changed(self) -> bool:
        return self.mtime != getmtime(self.filename)

    @cached_property
    def scope(self) -> SourceScope:
        source = Source(open(self.filename).read(), self.filename)
        scope = extract_scope(source, self.project)
        return scope

    @property
    def _attrs(self) -> dict[str, Object | Name]:
        return self.scope.exported_names  # type: ignore[return-value]


class ImportedModule(Object):
    def __init__(self, module: object) -> None:
        self.module = module
        self.changed = False

    @cached_property
    def _attrs(self) -> Attributes:
        return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.module))}
