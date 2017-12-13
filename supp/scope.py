from __future__ import print_function
import string
import logging
from bisect import bisect
from ast import Name as AstName, Attribute, Call, Str

from .util import (Location, np, insert_loc, cached_property,
                   get_indexes_for_target, context_property)
from .compat import PY2, itervalues, builtins, iteritems
from .name import (ArgumentName, MultiName, UndefinedName, ImportedName,
                   RuntimeName, AdditionalNameWrapper, AssignedName,
                   MultiValue, AssignedAttribute, Object, Resolvable,
                   Callable, ClassObject)
from . import compat

IMPORT_DELIMETERS = string.whitespace + '(,'
IMPORT_END_DELIMETERS = string.whitespace + '),.;'
UNRESOLVED = object()


class Scope(object):
    def __init__(self, parent, top=None):
        self.parent = parent
        self.top = top
        self.locals = set()
        self.globals = set()

    @property
    def filename(self):
        return self.top.source.filename


class Flow(object):
    def __init__(self, hint, scope, parents=None):
        self.hint = hint
        self.scope = scope
        self._names = []
        self.parents = parents or []

    def __repr__(self):
        return 'Flow({}, {})'.format(self.hint, self._names)

    def add_name(self, name):
        name.scope = self.scope
        if name.name in self.scope.globals:
            self.scope.top.add_global(name)
        else:
            self.scope.locals.add(name.name)
            insert_loc(self._names, name)

    @cached_property
    def names(self):
        return MergedDict({n.name: n for n in self._names}, self.parent_names)

    @cached_property
    def parent_names(self):
        if len(self.parents) == 1:
            return self.parents[0].names
        elif len(self.parents) > 1:
            names = {}
            nameset = set()
            pnames = [p.names for p in self.parents if p.names is not UNRESOLVED]
            for p in pnames:
                nameset.update(p)
            for n in nameset:
                nrow = set(r.get(n, UndefinedName(n)) for r in pnames)
                if len(nrow) == 1:
                    names[n] = list(nrow)[0]
                else:
                    names[n] = MultiName(list(nrow))
            return names
        else:
            pscope = self.scope.parent
            if pscope:
                pnames = pscope.names
                if isinstance(self.scope, ClassScope):
                    return MergedDict(pnames)
                else:
                    outer_names = set(pnames).difference(self.scope.locals)
                    return {n: pnames[n] for n in outer_names}
            else:
                return {}

    def names_at(self, loc):
        idx = bisect(self._names, Location(loc))
        return MergedDict({n.name: n for n in self._names[:idx]}, self.parent_names)

    def loop(self, to):
        self.parents.append(LoopFlow(to))


class LoopFlow(object):
    def __init__(self, parent):
        self.parent = parent
        self._resolving = False

    @property
    def names(self):
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
    def __init__(self, source):
        Scope.__init__(self, builtin_scope, self)
        self.source = source
        self.flow = Flow('top', self)
        self._all_flows = [self.flow]
        self._unvisited = []
        self._imports = []
        self._star_imports = []
        self._attr_assigns = []
        self._global_names = {}

    def __repr__(self):
        return 'SourceScope({})'.format(self.source.filename)

    @property
    def names(self):
        return MergedDict(self.flow.names, self._global_names)

    @property
    def exported_names(self):
        return {k: v
                for k, v in iteritems(self.names)
                if getattr(v, 'location', None) != (0, 0)}

    @property
    def all_names(self):
        for flow in self._all_flows:
            for name in flow._names:
                yield flow, name

    def add_unvisited(self, flow, node):
        self._unvisited.append((flow, node))

    def with_mark(self, position, debug=False):
        source = self.source.with_mark(position)
        return SourceScope(source)

    def find_id_loc(self, id, start, shift=0, delimeters=True):
        sl, pos = start
        source = '\n'.join(self.source.lines[sl-1:sl+50])
        source_len = len(source)
        while True:
            pos = source.find(id, pos + 1)
            if pos < 0:
                break

            if pos == 0 or not delimeters or source[pos-1] in IMPORT_DELIMETERS:
                ep = pos + len(id)
                if ep >= source_len or not delimeters or source[ep] in IMPORT_END_DELIMETERS:
                    return (sl + source.count('\n', 0, pos),
                            pos - source.rfind('\n', 0, pos) - 1 + shift)

        return start

    def add_attr_assign(self, scope, attr, value):
        self._attr_assigns.append((scope, attr, value))

    def add_global(self, name):
        self._global_names[name.name] = name

    def add_flow(self, flow):
        self._all_flows.append(flow)
        return flow

    @context_property
    def assigns(self, ctx):
        # logging.getLogger('supp.attr').error('Start assign')
        result = {}
        for _scope, attr, value in self._attr_assigns:
            # logging.getLogger('supp.attr').error('Get attr for %s %s',
            #                                      scope, dump(attr, annotate_fields=False))
            if type(attr.value) is AstName:
                attr_val = ctx.evaluate(attr.value)
                if attr_val:
                    attrs = result.setdefault(attr_val, {})
                    assigned_attr = AssignedAttribute(self, attr, value, np(attr))
                    try:
                        attrs[attr.attr].add(assigned_attr)
                    except KeyError:
                        attrs[attr.attr] = MultiValue(assigned_attr)

        return result

    def resolve_star_imports(self, project):
        for loc, declared_at, mname, flow in self._star_imports:
            try:
                module = project.get_nmodule(mname, self.filename)
            except ImportError:
                continue

            for name in itervalues(module.attrs):
                if not name.name.startswith('_'):
                    flow.add_name(ImportedName(name.name, loc, declared_at,
                                               mname, name.name, True))

        self._star_imports[:] = []


class FuncScope(Scope, Location, Callable):
    def __init__(self, parent, node, is_lambda=False, top=None):
        Scope.__init__(self, parent, top)
        self.args = []
        if is_lambda:
            self.name = 'lambda'
            self.location = np(node.body)
            self.declared_at = np(node)
        else:
            self.name = node.name
            self.declared_at = top.find_id_loc(' ' + node.name, np(node), 1, False)
            for n in node.body:
                if n.col_offset >= 0:
                    self.location = np(n)
                    break
            else:
                self.location = np(node.body[0])[0], np(node)[1] + 4

        for ni, n in enumerate(node.args.args):
            if PY2:
                for nn, idx in get_indexes_for_target(n, [], []):
                    self.args.append(ArgumentName([ni] + idx, nn.id, self.location, np(nn), self))
            else:
                self.args.append(ArgumentName([ni], n.arg, self.location, np(n), self))

        if not PY2:
            for n in node.args.kwonlyargs:
                self.args.append(ArgumentName([], n.arg, self.location, np(n), self))

        for s, n in (('*', node.args.vararg), ('**', node.args.kwarg)):
            if n:
                if PY2:
                    declared_at = top.find_id_loc(s + n, np(node), len(s))
                    self.args.append(ArgumentName([], n, self.location, declared_at, self))
                else:
                    self.args.append(ArgumentName([], n.arg, self.location, np(n), self))

        self.flow = self.top.add_flow(Flow('func', self))
        for arg in self.args:
            self.flow.add_name(arg)

        self.returns = []

    @property
    def names(self):
        return self.flow.names

    def get_argument(self, ctx, arg):
        if arg.idx == [0] and isinstance(self.parent, ClassScope):
            return self.parent.resolve(ctx).call(ctx)

    @context_property
    def call(self, ctx):
        if len(self.returns) == 1:
            return ctx.evaluate(self.returns[0])

    def __repr__(self):
        return 'FuncScope({}, {})'.format(self.name, self.declared_at)


class ClassScope(Scope, Location, Resolvable):
    def __init__(self, parent, node, top=None):
        Scope.__init__(self, parent, top)
        self.name = node.name
        self.declared_at = top.find_id_loc(' ' + node.name, np(node), 1, False)
        self.location = np(node.body[0])
        self.flow = self.top.add_flow(Flow('class', self))
        self._bases = node.bases

    @property
    def names(self):
        return self.parent.names

    @context_property
    def resolve(self, ctx):
        return ClassObject(ctx, self)

    def __repr__(self):
        return 'ClassScope({}, {})'.format(self.name, self.declared_at)


class BuiltinScope(object):
    @cached_property
    def names(self):
        names = {k: RuntimeName(k, v) for k, v in iteritems(vars(builtins))}
        names.update({k: RuntimeName(k, v)
                      for k, v in iteritems(vars(compat))
                      if k.startswith('__')})
        return names


builtin_scope = BuiltinScope()


class MergedDict(object):
    def __init__(self, *dicts):
        self._dicts = dd = []
        for d in dicts:
            if type(d) == MergedDict:
                dd.extend(d._dicts)
            else:
                dd.append(d)

    def __getitem__(self, key):
        for p in self._dicts:
            try:
                return p[key]
            except KeyError:
                pass

        raise KeyError(key)

    def __contains__(self, key):
        return any(key in p for p in self._dicts)

    def iteritems(self):
        result = {}
        for p in reversed(self._dicts):
            result.update(p)

        return iteritems(result)

    items = iteritems

    def __iter__(self):
        return (r[0] for r in self.iteritems())

    def itervalues(self):
        return (r[1] for r in self.iteritems())

    values = itervalues

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
