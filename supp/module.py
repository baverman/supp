from __future__ import annotations

import typing as t
from os.path import getmtime

from .compat import iteritems
from .name import Object, RuntimeName
from .nast import extract_scope
from .util import Source, cached_property, gen_doc

if t.TYPE_CHECKING:
    from .name import Attributes, Name
    from .project import Project
    from .scope import SourceScope


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
        self.declared_at = (3, 0)

    @cached_property
    def _attrs(self) -> Attributes:
        return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.module))}

    @property
    def filename(self) -> str:
        return gen_doc(self.module.__name__, self.module)  # type: ignore[attr-defined]
