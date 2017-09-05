import logging

from .util import Location, cached_property, context_property
from .compat import iteritems


class Object(object):
    pass


class Callable(object):
    pass


class Resolvable(object):
    pass


class Name(Location):
    def __init__(self, name, location=None):
        self.name = name
        self.location = location

    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__,
                                   self.name, self.location)

    @property
    def filename(self):
        return self.scope and self.scope.top.filename


class ArgumentName(Name, Resolvable):
    def __init__(self, idx, name, location, declared_at, func):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func
        self.idx = idx

    def __repr__(self):
        return 'ArgumentName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)

    @context_property
    def resolve(self, ctx):
        return self.func.get_argument(ctx, self)


class AssignedName(Name):
    def __init__(self, name, location, declared_at, value_node):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node

    def __repr__(self):
        return 'AssignedName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class AdditionalNameWrapper(Object):
    def __init__(self, value, names):
        self.value = value
        self._names = names

    @property
    def scope(self):
        return self.value.scope

    @property
    def declared_at(self):
        return self.value.declared_at

    @property
    def attrs(self):
        names = self._names.copy()
        if self.value:
            names.update(self.value.attrs)
        return names


class FailedImport(str):
    names = {}


class ImportedName(Name, Resolvable):
    def __init__(self, name, location, declared_at, module,
                 mname=None, is_star=False):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname
        self.is_star = is_star

    def resolve(self, ctx):
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
                value = FailedImport(self.module)
            else:
                if self.mname:
                    value = value.attrs.get(self.mname)

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
                value = AdditionalNameWrapper(value, names)

        self._ref = value
        return value

    def __repr__(self):
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname)


class RuntimeName(Name, Object, Callable):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.location = (0, 0)

    @cached_property
    def attrs(self):
        try:
            return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.value))}
        except TypeError:
            return {k: RuntimeName(k, getattr(self.value, k, None)) for k in dir(self.value)}

    def call(self, info):
        try:
            return self._instance
        except AttributeError:
            pass

        self._instance = None
        if isinstance(self.value, type):
            try:
                self._instance = RuntimeName(None, self.value())
            except TypeError:
                pass

        return self._instance


class UndefinedName(str):
    location = (0, 0)

    def __lt__(self, other):
        return True

    def __repr__(self):
        return 'UndefinedName({})'.format(self)


class MultiName(object):
    def __init__(self, names):
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.alt_names)
            else:
                allnames.append(n)
        self.alt_names = list(set(allnames))
        n = self.alt_names[0]
        if type(n) == UndefinedName:
            self.name = str(n)
        else:
            self.name = n.name

    def __repr__(self):
        return 'MultiName({})'.format(self.alt_names)


class AssignedAttribute(Name, Resolvable):
    def __init__(self, scope, attr, value, declared_at):
        self.name = attr.attr
        self.location = 0, 0
        self.attr = attr
        self.declared_at = declared_at
        self.scope = scope
        self.value = value

    @context_property
    def resolve(self, ctx):
        return ctx.evaluate(self.value)


class MultiValue(Object, Resolvable):
    def __init__(self, value):
        self.values = [value]

    def add(self, value):
        if isinstance(value, MultiValue):
            self.values.extend(value.values)
        else:
            self.values.append(value)
        return value

    @context_property
    def resolve(self, ctx):
        result = {}
        for v in self.values:
            val = v.resolve(ctx)
            val and result.update(val.attrs)
        return AttrObject(result)


class ClassObject(Object, Callable):
    def __init__(self, ctx, scope):
        self.ctx = ctx
        self.scope = scope

    @property
    def _attrs(self):
        names = self.scope.flow.names
        return {n: names[n] for n in self.scope.locals}

    @cached_property
    def bases(self):
        return list(filter(None, (self.ctx.evaluate(r) for r in self.scope._bases)))

    @cached_property
    def attrs(self):
        attrs = {}
        for b in reversed(self.bases):
            attrs.update(b.attrs)
        attrs.update(self._attrs)
        return attrs

    @context_property
    def call(self, ctx):
        return InstanceValue(ctx, self)


class InstanceValue(Object):
    def __init__(self, ctx, cls):
        self.ctx = ctx
        self.cls = cls

    @cached_property
    def attrs(self):
        attrs = self.cls.attrs.copy()
        for b in reversed(self.cls.bases):
            attrs.update(b.call(self.ctx).attrs)
        attrs.update(self.cls.scope.top.assigns(self.ctx).get(self, {}))
        return attrs


class AttrObject(Object):
    def __init__(self, attrs):
        self.attrs = attrs
