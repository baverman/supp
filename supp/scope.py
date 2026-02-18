from __future__ import annotations

import string
import typing as t
from ast import AST, Attribute, ClassDef, FunctionDef, Lambda, expr, stmt
from ast import Name as AstName
from bisect import bisect

from . import compat
from .compat import PY2, builtins, iteritems, iterkeys
from .merged_dict import MergedDict
from .name import (
    AnnotatedName,
    ArgumentName,
    AssignedAttribute,
    ClassObject,
    FuncObject,
    ImportedName,
    MultiName,
    MultiValue,
    Name,
    Object,
    Resolvable,
    RuntimeName,
    UndefinedName,
    first_name,
)
from .util import (
    Location,
    Source,
    cached_property,
    context_property,
    get_indexes_for_target,
    insert_loc,
    loc_t,
    np,
)

if t.TYPE_CHECKING:
    from .evaluator import EvalCtx
    from .project import Project

IMPORT_DELIMETERS = string.whitespace + '(,'
IMPORT_END_DELIMETERS = string.whitespace + '),.;'


class Unresolved(object):
    pass


UNRESOLVED = Unresolved()


class BaseScope(object):
    @property
    def names(self) -> t.Mapping[str, Name | MultiName]:
        raise NotImplementedError


class Scope(BaseScope):
    flow: 'Flow'

    def __init__(self, parent: 'Scope', top: 'SourceScope') -> None:
        self.parent = parent
        self.top = top
        self.locals: set[str] = set()
        self.globals: set[str] = set()
        self.annotations: dict[str, AnnotatedName] = {}

    @property
    def filename(self) -> str:
        return self.top.source.filename


class Flow(object):
    def __init__(
        self, hint: str, scope: Scope, parents: t.MutableSequence[Flow | LoopFlow] | None = None
    ) -> None:
        self.hint = hint
        self.scope = scope
        self._names: list[Name] = []
        self.parents: t.MutableSequence[Flow | LoopFlow] = parents or []

    def __repr__(self) -> str:
        return 'Flow({}, {})'.format(self.hint, self._names)

    def add_name(self, name: Name) -> None:
        name.scope = self.scope
        if name.name in self.scope.globals:
            self.scope.top.add_global(name)
        else:
            self.scope.locals.add(name.name)
            insert_loc(self._names, name)

    @cached_property
    def names(self) -> t.Mapping[str, Name | MultiName]:
        return MergedDict({n.name: n for n in self._names}, self.parent_names)

    @cached_property
    def parent_names(self) -> t.Mapping[str, Name | MultiName]:
        if len(self.parents) == 1:
            return self.parents[0].names  # type: ignore[return-value]
        elif len(self.parents) > 1:
            names: dict[str, Name | MultiName] = {}
            nameset: set[str] = set()
            pnames: list[t.Mapping[str, Name]] = [
                p.names  # type: ignore[misc]
                for p in self.parents
                if p.names is not UNRESOLVED
            ]
            for p in pnames:
                nameset.update(p)
            for n in nameset:
                nrow = set(r.get(n, UndefinedName(n)) for r in pnames)
                if len(nrow) == 1:
                    # single undefined names is not possible
                    names[n] = list(nrow)[0]  # type: ignore[assignment]
                else:
                    names[n] = MultiName(list(nrow))
            return names
        else:
            pscope = self.scope.parent
            if pscope:
                snames = pscope.names
                if isinstance(self.scope, ClassScope):
                    return MergedDict(snames)
                else:
                    outer_names = set(snames).difference(self.scope.locals)
                    return {n: snames[n] for n in outer_names}
            else:
                return {}

    def names_at(self, loc: loc_t) -> t.Mapping[str, Name | MultiName]:
        idx = bisect(self._names, Location(loc))
        return MergedDict({n.name: n for n in self._names[:idx]}, self.parent_names)

    def loop(self, to: Flow) -> None:
        self.parents.append(LoopFlow(to))


class LoopFlow(object):
    _names: t.Mapping[str, Name | MultiName]

    def __init__(self, parent: Flow) -> None:
        self.parent = parent
        self._resolving = False

    @property
    def names(self) -> t.Mapping[str, Name | MultiName] | Unresolved:
        if self._resolving:
            return UNRESOLVED

        try:
            return self._names
        except AttributeError:
            pass

        self._resolving = True
        try:
            result = self._names = self.parent.names
        finally:
            self._resolving = False

        return result


class SourceScope(Scope):
    _imports: list[str]
    _global_names: dict[str, Name]
    _attr_assigns: list[tuple[Scope, Attribute, AST, expr | None]]
    _star_imports: list[tuple[loc_t, loc_t, str, Flow]]
    _unvisited: list[tuple[Flow, AST]]
    source: Source

    def __init__(self, source: Source) -> None:
        Scope.__init__(self, builtin_scope, self)  # type: ignore[arg-type]
        self.source = source
        self.flow = Flow('top', self)
        self._all_flows = [self.flow]
        self._unvisited = []
        self._imports = []
        self._star_imports = []
        self._attr_assigns = []
        self._global_names = {}

    def __repr__(self) -> str:
        return 'SourceScope({})'.format(self.source.filename)

    @property
    def names(self) -> t.Mapping[str, Name | MultiName]:
        return MergedDict(self.flow.names, self._global_names)

    @property
    def exported_names(self) -> dict[str, Name]:
        return {
            k: first_name(v)
            for k, v in iteritems(self.names)
            if getattr(v, 'location', None) != (0, 0)
        }

    @property
    def all_names(self) -> t.Iterable[tuple[Flow, Name]]:
        for flow in self._all_flows:
            for name in flow._names:
                yield flow, name

    def add_unvisited(self, flow: Flow, node: AST) -> None:
        self._unvisited.append((flow, node))

    def with_mark(self, position: tuple[int, int], debug: bool = False) -> 'SourceScope':
        source = self.source.with_mark(position)
        return SourceScope(source)

    def find_id_loc(self, id: str, start: loc_t, shift: int = 0, delimeters: bool = True) -> loc_t:
        sl, pos = start
        source = '\n'.join(self.source.lines[sl - 1 : sl + 50])
        source_len = len(source)
        while True:
            pos = source.find(id, pos + 1)
            if pos < 0:
                break

            if pos == 0 or not delimeters or source[pos - 1] in IMPORT_DELIMETERS:
                ep = pos + len(id)
                if ep >= source_len or not delimeters or source[ep] in IMPORT_END_DELIMETERS:
                    return (
                        sl + source.count('\n', 0, pos),
                        pos - source.rfind('\n', 0, pos) - 1 + shift,
                    )

        return start

    def add_attr_assign(
        self, scope: Scope, attr: Attribute, value: AST, annotation: expr | None = None
    ) -> None:
        self._attr_assigns.append((scope, attr, value, annotation))

    def add_global(self, name: Name) -> None:
        self._global_names[name.name] = name

    def add_flow(self, flow: Flow) -> Flow:
        self._all_flows.append(flow)
        return flow

    @context_property
    def assigns(self, ctx: EvalCtx) -> dict[Object, dict[str, MultiValue]]:
        result: dict[Object, dict[str, MultiValue]] = {}
        for _scope, attr, value, annotation in self._attr_assigns:
            # logging.getLogger('supp.attr').error('Get attr for %s %s',
            #                                      scope, dump(attr, annotate_fields=False))
            if type(attr.value) is AstName:
                attr_val = ctx.evaluate(attr.value)
                if attr_val:
                    attrs = result.setdefault(attr_val, {})
                    assigned_attr = AssignedAttribute(self, attr, value, np(attr), annotation)
                    try:
                        attrs[attr.attr].add(assigned_attr)
                    except KeyError:
                        attrs[attr.attr] = MultiValue(assigned_attr)

        return result

    def resolve_star_imports(self, project: Project) -> None:
        for loc, declared_at, mname, flow in self._star_imports:
            try:
                module = project.get_nmodule(mname, self.filename)
            except ImportError:
                continue

            for name in iterkeys(module._attrs):
                if not name.startswith('_'):
                    flow.add_name(ImportedName(name, loc, declared_at, mname, name, True))

        self._star_imports[:] = []


def get_first_body_node_loc(body: list[stmt]) -> loc_t | None:
    if not body:
        return None

    if type(body[0]) in (FunctionDef, ClassDef) and body[0].decorator_list:  # type: ignore[attr-defined]
        return body[0].decorator_list[0].lineno, body[0].col_offset  # type: ignore[attr-defined]

    for n in body:
        if n.col_offset >= 0:
            return np(n)

    return None


class FuncScope(Scope, Location, Resolvable):
    def __init__(self, parent: Scope, node: FunctionDef | Lambda, top: SourceScope) -> None:
        Scope.__init__(self, parent, top)
        self.args = []
        self.node = node
        if type(node) is Lambda:
            self.name = 'lambda'
            self.location = np(node.body)
            self.declared_at = np(node)
            self.decorator_list = []
        else:
            fnode: FunctionDef = node  # type: ignore[assignment]
            self.name = fnode.name
            self.declared_at = top.find_id_loc(' ' + fnode.name, np(fnode), 1, False)
            self.location = get_first_body_node_loc(fnode.body) or (
                np(fnode.body[0])[0],
                np(fnode)[1] + 4,
            )
            self.decorator_list = fnode.decorator_list

        for ni, n in enumerate(node.args.args):
            if PY2:
                for nn, idx in get_indexes_for_target(n, [], []):
                    self.args.append(ArgumentName([ni] + idx, nn.id, self.location, np(nn), self))
            else:
                self.args.append(
                    ArgumentName([ni], n.arg, self.location, np(n), self, n.annotation)
                )

        if not PY2:
            for n in node.args.kwonlyargs:
                self.args.append(ArgumentName([], n.arg, self.location, np(n), self))

        for s, n in (('*', node.args.vararg), ('**', node.args.kwarg)):  # type: ignore[assignment]
            if n:
                if PY2:
                    declared_at = top.find_id_loc(s + n, np(node), len(s))
                    self.args.append(ArgumentName([], n, self.location, declared_at, self))
                else:
                    self.args.append(ArgumentName([], n.arg, self.location, np(n), self))

        self.flow = self.top.add_flow(Flow('func', self))
        for arg in self.args:
            self.flow.add_name(arg)

        self.returns: list[AST] = []

    @property
    def names(self) -> t.Mapping[str, Name | MultiName]:
        return self.flow.names

    def get_argument(self, ctx: EvalCtx, arg: ArgumentName) -> Object | None:
        if arg.idx == [0] and isinstance(self.parent, ClassScope):
            return self.parent.resolve(ctx).call(ctx)
        if arg.annotation:
            return ctx.evaluate_annotation(arg.annotation, self.parent.flow)[0]
        return None

    def resolve(self, ctx: EvalCtx) -> Object | None:
        o = FuncObject(self)
        if not isinstance(self.parent, ClassScope):
            return o

        for d in self.decorator_list:
            v = ctx.evaluate(d)
            if isinstance(v, RuntimeName) and v.is_builtin and v.name == 'property':
                return o.call(ctx)
            if isinstance(v, ClassObject) and '__get__' in v._attrs:
                return o.call(ctx)

        return o

    def __repr__(self) -> str:
        return 'FuncScope({}, {})'.format(self.name, self.declared_at)


class ClassScope(Scope, Location, Resolvable):
    def __init__(self, parent: Scope, node: ClassDef, top: SourceScope) -> None:
        Scope.__init__(self, parent, top)
        self.name = node.name
        self.declared_at = top.find_id_loc(' ' + node.name, np(node), 1, False)
        self.location = np(node.body[0])
        self.flow = self.top.add_flow(Flow('class', self))
        self._bases = node.bases

    @property
    def names(self) -> t.Mapping[str, Name | MultiName]:
        return self.parent.names

    @context_property
    def resolve(self, ctx: EvalCtx) -> ClassObject:
        return ClassObject(ctx, self)

    def __repr__(self) -> str:
        return 'ClassScope({}, {})'.format(self.name, self.declared_at)


class BuiltinScope(BaseScope):
    @cached_property
    def names(self) -> dict[str, Name]:
        names = {k: RuntimeName(k, v, True) for k, v in iteritems(vars(builtins))}
        names.update(
            {k: RuntimeName(k, v) for k, v in iteritems(vars(compat)) if k.startswith('__')}
        )
        return names  # type: ignore[return-value]


builtin_scope = BuiltinScope()
