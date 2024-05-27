import logging

from .util import Location, cached_property, context_property
from .compat import iteritems

if False:
    import typing as t
    import ast
    from .scope import Scope, ClassScope, SourceScope, FuncScope
    from .evaluator import EvalCtx
    from .util import loc_t
    from .module import SourceModule, ImportedModule
    AttrList = t.Mapping[str, t.Any] | list[str] | set[str]
    Attributes = dict[str, 'Object | Name']
    Names = t.Mapping[str, 'Name']

    class CallableProto(t.Protocol):
        @property
        def _attrs(self): # type: () -> Attributes
            ...

        def call(self, ctx):  # type: (EvalCtx) -> Object | None
            ...



class Object(object):
    def attr_list(self, ctx):
        # type: (EvalCtx) -> AttrList
        return self._attrs

    def get_attr(self, ctx, name):
        # type: (EvalCtx, str) -> 'Object' | 'Name' | None
        return self._attrs.get(name)

    if False:
        @property
        def _attrs(self): # type: () -> Attributes
            raise NotImplementedError


class Callable(object):
    pass


class Resolvable(object):
    pass


class Name(Location):
    if False:
        scope = None  # type: Scope

    def __init__(self, name, location):
        # type: (str, loc_t) -> None
        self.name = name
        self.location = location

    def __repr__(self):
        # type: () -> str
        return '{}({}, {})'.format(self.__class__.__name__,
                                   self.name, self.location)

    @property
    def filename(self):
        # type: () -> str | None
        if self.scope:
            return self.scope.top.source.filename
        return None


class ArgumentName(Name, Resolvable):
    def __init__(self, idx, name, location, declared_at, func):
        # type: (list[int], str, loc_t, loc_t, FuncScope) -> None
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func
        self.idx = idx

    def __repr__(self):
        # type: () -> str
        return 'ArgumentName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)

    @context_property
    def resolve(self, ctx):
        # type: (EvalCtx) -> Object | None
        return self.func.get_argument(ctx, self)


class AssignedName(Name):
    def __init__(self, name, location, declared_at, value_node):
        # type: (str, loc_t, loc_t, ast.AST) -> None
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node

    def __repr__(self):
        # type: () -> str
        return 'AssignedName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class AdditionalNameWrapper(Object):
    def __init__(self, value, names):
        # type: (SourceModule | ImportedModule, t.Mapping[str, Name]) -> None
        self.value = value
        self._names = names

    # @property
    # def scope(self):
    #     return self.value.scope

    @property
    def declared_at(self):
        # type: () -> loc_t
        return self.value.declared_at  # type: ignore[union-attr] # TODO

    def attr_list(self, ctx):
        # type: (EvalCtx) -> AttrList
        if self.value:
            return set(self._names) | set(self.value.attr_list(ctx))
        else:
            return self._names

    def get_attr(self, ctx, name):
        # type: (EvalCtx, str) -> Object | Name | None
        if self.value:
            return self.value.get_attr(ctx, name) or self._names.get(name)
        return None


class CompositeValue(Object):
    def __init__(self, values):
        # type: (list[Object]) -> None
        self.values = values

    def attr_list(self, ctx):
        # type: (EvalCtx) -> set[str]
        result = set()  # type: set[str]
        for v in self.values:
            result.update(v.attr_list(ctx))
        return result

    def get_attr(self, ctx, name):
        # type: (EvalCtx, str) -> Object | Name | None
        for v in self.values:
            result = v.get_attr(ctx, name)
            if result is not None:
                return result
        return None


# class FailedImport(str):
#     names = {}


class ImportedName(Name, Resolvable):
    if False:
        _ref = None   # type: Object | None
        scope = None  # type: SourceScope

    def __init__(self, name, location, declared_at, module,
                 mname=None, is_star=False, qualified=False):
        # type: (str, loc_t, loc_t, str, str | None, bool, bool) -> None
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname
        self.is_star = is_star
        self.qualified = qualified

    def resolve(self, ctx):
        # type: (EvalCtx) -> Object | None
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
                    'Failed import of %s from %s', self.module, filename)
                # value = FailedImport(self.module)
            else:
                if self.mname:
                    value = value.get_attr(ctx, self.mname)  # type: ignore[assignment]

        if not self.mname and value:
            prefix = self.module + '.'
            names = {}
            for mname in self.scope.top._imports:
                if mname.startswith(prefix):
                    name = mname[len(prefix):].partition('.')[0]
                    names[name] = iname = ImportedName(name, (0, 0), (0, 0),
                                                       prefix + name, None)
                    iname.scope = self.scope
            if names:
                value = AdditionalNameWrapper(value, names)  # type: ignore[assignment]

        self._ref = value
        return value

    def __repr__(self):  # type: () -> str
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname)


class RuntimeName(Name, Object, Callable):
    if False:
        _instance = None  # type: Object | None

    def __init__(self, name, value, is_builtin=False):
        # type: (str, t.Any, bool) -> None
        self.name = name
        self.value = value
        self.location = (0, 0)
        self.is_builtin = is_builtin

    @cached_property
    def _attrs(self):
        # type: () -> Attributes
        try:
            return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.value))}
        except TypeError:
            return {k: RuntimeName(k, getattr(self.value, k, None)) for k in dir(self.value)}

    def call(self, ctx):
        # type: (EvalCtx) -> Object | None
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


class UndefinedName(str):
    location = (0, 0)

    def __lt__(self, other):  # type: (t.Any) -> bool
        return True

    def __repr__(self):  # type: () -> str
        return 'UndefinedName({})'.format(self)

    @property
    def name(self):  # type: () -> str
        return str(self)


class MultiName(object):
    def __init__(self, names):
        # type: (list[Name | UndefinedName]) -> None
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.alt_names)
            else:
                allnames.append(n)
        self.alt_names = list(set(allnames))
        self.name = self.alt_names[0].name

    def __repr__(self):  # type: () -> str
        return 'MultiName({})'.format(self.alt_names)

    @cached_property
    def has_undefined(self):
        # type: () -> bool
        return any(type(it) is UndefinedName for it in self.alt_names)

    @cached_property
    def valid_names(self):
        # type: () -> list[Name]
        return [it for it in self.alt_names if type(it) is not UndefinedName]  # type: ignore[misc]


class AssignedAttribute(Name, Resolvable):
    def __init__(self, scope, attr, value, declared_at):
        # type: (SourceScope, ast.Attribute, ast.AST, loc_t) -> None
        self.name = attr.attr
        self.location = 0, 0
        self.attr = attr
        self.declared_at = declared_at
        self.scope = scope
        self.value = value

    @context_property
    def resolve(self, ctx):
        # type: (EvalCtx) -> Object | None
        return ctx.evaluate(self.value)


class MultiValue(Object):
    if False:
        _rvalues = None  # type: list[Object]

    def __init__(self, value):
        # type: (AssignedAttribute) -> None
        self.values = [value]

    def add(self, value):
        # type: (MultiValue | AssignedAttribute) -> MultiValue | AssignedAttribute
        if isinstance(value, MultiValue):
            self.values.extend(value.values)
        else:
            self.values.append(value)
        return value

    def get_rvalues(self, ctx):
        # type: (EvalCtx) -> list[Object]
        try:
            return self._rvalues
        except AttributeError:
            pass

        result = self._rvalues = list(filter(None, (
            v.resolve(ctx) for v in self.values)))
        return result

    def attr_list(self, ctx):
        # type: (EvalCtx) -> AttrList
        result: set[str] = set()
        for v in self.get_rvalues(ctx):
            result.update(v.attr_list(ctx))
        return result

    def get_attr(self, ctx, name):
        # type: (EvalCtx, str) -> Object | Name | None
        for v in self.get_rvalues(ctx):
            result = v.get_attr(ctx, name)
            if result is not None:
                return result
        return None


class ClassObject(Object, Callable):
    def __init__(self, ctx, scope):
        # type: (EvalCtx, ClassScope) -> None
        self.ctx = ctx
        self.scope = scope

    @property
    def _cls_attrs(self):
        # type: () -> Names
        names = self.scope.flow.names
        return {n: names[n] for n in self.scope.locals}  # type: ignore[misc]  # TODO: could be MultiName

    @cached_property
    def bases(self):
        # type: () -> list[CallableProto]
        return list(filter(None, (self.ctx.evaluate(r) for r in self.scope._bases)))  # type: ignore[misc]

    @cached_property
    def _attrs(self):
        # type: () -> Attributes
        attrs = {}
        for b in reversed(self.bases):
            attrs.update(b._attrs)
        attrs.update(self._cls_attrs)
        return attrs

    @context_property
    def call(self, ctx):
        # type: (EvalCtx) -> InstanceValue
        return InstanceValue(ctx, self)


class FuncObject(Object, Callable):
    def __init__(self, scope):
        # type: (FuncScope) -> None
        self.scope = scope

    @cached_property
    def _attrs(self):
        # type: () -> Attributes
        return {}

    @context_property
    def call(self, ctx):
        # type: (EvalCtx) -> Object | None
        if len(self.scope.returns) == 1:
            return ctx.evaluate(self.scope.returns[0])
        return None


class InstanceValue(Object):
    def __init__(self, ctx, cls):
        # type: (EvalCtx, ClassObject) -> None
        self.ctx = ctx
        self.cls = cls

    @cached_property
    def _attrs(self):
        # type: () -> Attributes
        attrs = self.cls._attrs.copy()
        for b in reversed(self.cls.bases):
            o = b.call(self.ctx)
            if o:
                attrs.update(o._attrs)
        attrs.update(self.cls.scope.top.assigns(self.ctx).get(self, {}))
        return attrs


class AttrObject(Object):
    def __init__(self, attrs): # type: (Attributes) -> None
        self._attrs = attrs  # type: ignore[misc]


def first_name(name):
    # type: (Name | MultiName) -> Name
    if type(name) is MultiName:
        return name.valid_names[0]
    return name  # type: ignore[return-value]
