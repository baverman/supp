from __future__ import annotations

import ast
import logging
import typing as t

from .ast_types import Annotation, make_annotation
from .compat import iteritems
from .util import Location, cached_property, context_property, gen_doc

if t.TYPE_CHECKING:
    from .evaluator import AnnotationEvalResult, EvalCtx
    from .module import ImportedModule, SourceModule
    from .scope import ClassScope, FuncScope, Scope, SourceScope
    from .util import loc_t

AttrList = t.Mapping[str, t.Any] | list[str] | set[str]
Attributes = dict[str, 'Object | Name']
Names = t.Mapping[str, 'Name']


class CallableProto(t.Protocol):
    @property
    def _attrs(self) -> Attributes: ...

    def call(self, ctx: EvalCtx) -> Object | None: ...


class Object(object):
    def attr_list(self, ctx: EvalCtx) -> AttrList:
        return self._attrs

    def get_attr(self, ctx: EvalCtx, name: str) -> 'Object' | 'Name' | None:
        return self._attrs.get(name)

    @property
    def _attrs(self) -> Attributes:
        raise NotImplementedError


class Callable(object):
    def call(self, ctx: EvalCtx) -> Object | None: ...


class Resolvable(object):
    pass


class Name(Location):
    scope: Scope
    declared_at: loc_t
    used: bool

    def __init__(self, name: str, location: loc_t) -> None:
        self.name = name
        self.location = location

    def __repr__(self) -> str:
        return '{}({}, {})'.format(self.__class__.__name__, self.name, self.location)

    @property
    def filename(self) -> str | None:
        if self.scope:
            return self.scope.top.source.filename
        return None


class ArgumentName(Name, Resolvable):
    def __init__(
        self,
        idx: list[int],
        name: str,
        location: loc_t,
        declared_at: loc_t,
        func: FuncScope,
        annotation: Annotation | None = None,
    ) -> None:
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func
        self.idx = idx
        self.annotation = annotation

    def __repr__(self) -> str:
        return 'ArgumentName({}, {}, {})'.format(self.name, self.location, self.declared_at)

    @context_property
    def resolve(self, ctx: EvalCtx) -> Object | None:
        return self.func.get_argument(ctx, self)


class AssignedName(Name):
    def __init__(
        self,
        name: str,
        location: loc_t,
        declared_at: loc_t,
        value_node: ast.AST,
        annotation: Annotation | None = None,
    ) -> None:
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node
        self.annotation = annotation

    def __repr__(self) -> str:
        return 'AssignedName({}, {}, {})'.format(self.name, self.location, self.declared_at)


class AnnotatedName(Name, Resolvable):
    def __init__(self, name: str, location: loc_t, declared_at: loc_t, annotation: Annotation):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.annotation = annotation

    def __repr__(self) -> str:
        return 'AnnotatedName({}, {}, {})'.format(self.name, self.location, self.declared_at)

    @context_property
    def resolve_full(self, ctx: EvalCtx) -> AnnotationEvalResult:
        return ctx.evaluate_annotation(self.annotation)

    def resolve(self, ctx: EvalCtx) -> Object | None:
        return self.resolve_full(ctx).type


class AnnotatedWrapper(Name, Resolvable):
    def __init__(self, obj: Name | Object, annotation: AnnotatedName):
        self.object = obj
        self.annotation = annotation

    def resolve(self, ctx: EvalCtx) -> Object | None:
        return self.annotation.resolve(ctx)


class AdditionalNameWrapper(Object):
    def __init__(self, value: SourceModule | ImportedModule, names: t.Mapping[str, Name]) -> None:
        self.value = value
        self._names = names

    # @property
    # def scope(self):
    #     return self.value.scope

    @property
    def declared_at(self) -> loc_t:
        return self.value.declared_at

    def attr_list(self, ctx: EvalCtx) -> AttrList:
        if self.value:
            return set(self._names) | set(self.value.attr_list(ctx))
        else:
            return self._names

    def get_attr(self, ctx: EvalCtx, name: str) -> Object | Name | None:
        if self.value:
            return self.value.get_attr(ctx, name) or self._names.get(name)
        return None


class CompositeValue(Object):
    def __init__(self, values: list[Object]) -> None:
        self.values = values

    def attr_list(self, ctx: EvalCtx) -> set[str]:
        result: set[str] = set()
        for v in self.values:
            result.update(v.attr_list(ctx))
        return result

    def get_attr(self, ctx: EvalCtx, name: str) -> Object | Name | None:
        for v in self.values:
            result = v.get_attr(ctx, name)
            if result is not None:
                return result
        return None


# class FailedImport(str):
#     names = {}


class ImportedName(Name, Resolvable):
    _ref: Object | None
    scope: SourceScope

    def __init__(
        self,
        name: str,
        location: loc_t,
        declared_at: loc_t,
        module: str,
        mname: str | None = None,
        is_star: bool = False,
        qualified: bool = False,
    ) -> None:
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname
        self.is_star = is_star
        self.qualified = qualified

    def resolve(self, ctx: EvalCtx) -> Object | None:
        try:
            return self._ref
        except AttributeError:
            pass

        value = None
        filename = self.scope.top.source.filename
        if self.mname:
            if self.module.strip('.'):
                module = self.module + '.' + self.mname
            else:
                module = self.module + self.mname

            try:
                value = ctx.project.get_nmodule(module, filename)
            except ImportError:
                pass

        if value is None:
            try:
                value = ctx.project.get_nmodule(self.module, filename)
            except ImportError:
                logging.getLogger('supp.import').error(
                    'Failed import of %s from %s', self.module, filename
                )
                # value = FailedImport(self.module)
            else:
                if self.mname:
                    value = value.get_attr(ctx, self.mname)  # type: ignore[assignment]

        if not self.mname and value:
            prefix = self.module + '.'
            names = {}
            for mname in self.scope.top._imports:
                if mname.startswith(prefix):
                    name = mname[len(prefix) :].partition('.')[0]
                    names[name] = iname = ImportedName(name, (0, 0), (0, 0), prefix + name, None)
                    iname.scope = self.scope
            if names:
                value = AdditionalNameWrapper(value, names)  # type: ignore[assignment]

        self._ref = value
        return value

    def __repr__(self) -> str:
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname
        )


class RuntimeName(Name, Object, Callable):
    _instance: Object | None

    def __init__(self, name: str, value: t.Any, is_builtin: bool = False) -> None:
        self.name = name
        self.value = value
        self.location = (0, 0)
        self.is_builtin = is_builtin
        self.declared_at = (3, 0)

    @cached_property
    def _attrs(self) -> Attributes:
        try:
            return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.value))}
        except TypeError:
            return {k: RuntimeName(k, getattr(self.value, k, None)) for k in dir(self.value)}

    def call(self, ctx: EvalCtx) -> Object | None:
        try:
            return self._instance
        except AttributeError:
            pass

        self._instance = None
        if isinstance(self.value, type):
            try:
                self._instance = RuntimeName('__none__', self.value())
            except TypeError:
                pass

        return self._instance

    @property
    def filename(self) -> str:
        return gen_doc(self.name, self.value)


class UndefinedName(str):
    location = (0, 0)
    used: bool

    def __lt__(self, other: t.Any) -> bool:
        return True

    def __repr__(self) -> str:
        return 'UndefinedName({})'.format(self)

    @property
    def name(self) -> str:
        return str(self)


class MultiName(object):
    def __init__(self, names: list[Name | UndefinedName]) -> None:
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.alt_names)
            else:
                allnames.append(n)
        self.alt_names = list(set(allnames))
        self.name = self.alt_names[0].name

    def __repr__(self) -> str:
        return 'MultiName({})'.format(self.alt_names)

    @cached_property
    def has_undefined(self) -> bool:
        return any(type(it) is UndefinedName for it in self.alt_names)

    @cached_property
    def valid_names(self) -> list[Name]:
        return [it for it in self.alt_names if type(it) is not UndefinedName]  # type: ignore[misc]


class AssignedAttribute(Name, Resolvable):
    def __init__(
        self,
        scope: SourceScope,
        attr: ast.Attribute,
        value: ast.AST,
        declared_at: loc_t,
        annotation: Annotation | None,
    ) -> None:
        self.name = attr.attr
        self.location = 0, 0
        self.attr = attr
        self.declared_at = declared_at
        self.scope = scope
        self.value = value
        self.annotation = annotation

    @context_property
    def resolve(self, ctx: EvalCtx) -> Object | None:
        if self.annotation:
            return ctx.evaluate_annotation(self.annotation).type
        return ctx.evaluate(self.value)


class MultiValue(Object):
    _rvalues: list[Object]

    def __init__(self, value: AssignedAttribute) -> None:
        self.values = [value]

    def add(self, value: MultiValue | AssignedAttribute) -> MultiValue | AssignedAttribute:
        if isinstance(value, MultiValue):
            self.values.extend(value.values)
        else:
            self.values.append(value)
        return value

    def get_rvalues(self, ctx: EvalCtx) -> list[Object]:
        try:
            return self._rvalues
        except AttributeError:
            pass

        result = self._rvalues = list(filter(None, (v.resolve(ctx) for v in self.values)))
        return result

    def attr_list(self, ctx: EvalCtx) -> AttrList:
        result: set[str] = set()
        for v in self.get_rvalues(ctx):
            result.update(v.attr_list(ctx))
        return result

    def get_attr(self, ctx: EvalCtx, name: str) -> Object | Name | None:
        for v in self.get_rvalues(ctx):
            result = v.get_attr(ctx, name)
            if result is not None:
                return result
        return None


class ClassObject(Object, Callable):
    def __init__(self, ctx: EvalCtx, scope: ClassScope) -> None:
        self.ctx = ctx
        self.scope = scope

    @property
    def _cls_attrs(self) -> Names:
        names = self.scope.flow.names
        return {n: names[n] for n in self.scope.locals}  # type: ignore[misc]  # TODO: could be MultiName

    @cached_property
    def bases(self) -> list[CallableProto]:
        return list(filter(None, (self.ctx.evaluate(r) for r in self.scope._bases)))  # type: ignore[misc]

    @cached_property
    def _attrs(self) -> Attributes:
        attrs = {}
        for b in reversed(self.bases):
            attrs.update(b._attrs)

        cls_attrs: dict[str, Name | Object] = self._cls_attrs  # type: ignore[assignment]
        annotations = self.scope.annotations
        for key, value in annotations.items():
            res = value.resolve_full(self.ctx)
            if res.type and res.is_class_var:
                attr = cls_attrs.get('key')
                if attr is not None:
                    cls_attrs[key] = AnnotatedWrapper(attr, value)
                else:
                    cls_attrs[key] = value
        attrs.update(cls_attrs)
        return attrs

    @context_property
    def call(self, ctx: EvalCtx) -> InstanceValue:
        return InstanceValue(ctx, self)


class FuncObject(Object, Callable):
    def __init__(self, scope: FuncScope) -> None:
        self.scope = scope

    @cached_property
    def _attrs(self) -> Attributes:
        return {}

    @context_property
    def call(self, ctx: EvalCtx) -> Object | None:
        node = self.scope.node
        if type(node) is ast.FunctionDef and node.returns:
            return ctx.evaluate_annotation(
                make_annotation(node.returns, self.scope.parent.flow)
            ).type
        if len(self.scope.returns) == 1:
            return ctx.evaluate(self.scope.returns[0])
        return None


class InstanceValue(Object):
    def __init__(self, ctx: EvalCtx, cls: ClassObject) -> None:
        self.ctx = ctx
        self.cls = cls

    @cached_property
    def _attrs(self) -> Attributes:
        attrs = self.cls._attrs.copy()
        for b in reversed(self.cls.bases):
            o = b.call(self.ctx)
            if o:
                attrs.update(o._attrs)

        attrs.update(self.cls.scope.top.assigns(self.ctx).get(self, {}))

        for key, value in self.cls.scope.annotations.items():
            res = value.resolve_full(self.ctx)
            if res.type and not res.is_class_var:
                attr = attrs.get(key)
                if attr is not None:
                    attrs[key] = AnnotatedWrapper(attr, value)
                else:
                    attrs[key] = value

        return attrs


class AttrObject(Object):
    def __init__(self, attrs: Attributes) -> None:
        self._attrs = attrs  # type: ignore[misc]


def first_name(name: Name | MultiName) -> Name:
    if type(name) is MultiName:
        return name.valid_names[0]
    return name  # type: ignore[return-value]
