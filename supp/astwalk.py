from bisect import bisect
from collections import defaultdict
from contextlib import contextmanager
from ast import NodeVisitor, Attribute, Tuple, List, Subscript

from .util import Location, np, get_expr_end, insert_loc, cached_property, Name
from .compat import PY2, itervalues, builtins
from . import compat

NESTED_INDEXED_NODES = Tuple, List
UNSUPPORTED_ASSIGMENTS = Attribute, Subscript


def get_indexes_for_target(target, result, idx):
    if isinstance(target, NESTED_INDEXED_NODES):
        idx.append(0)
        for r in target.elts:
            get_indexes_for_target(r, result, idx)
        idx.pop()
    else:
        result.append((target, idx[:]))
        if idx:
            idx[-1] += 1

    return result


class ArgumentName(Name):
    def __init__(self, name, location, declared_at, func):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func

    def __repr__(self):
        return 'ArgumentName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class AssignedName(Name):
    def __init__(self, name, location, declared_at, value_node):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node

    def __repr__(self):
        return 'AssignedName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class ImportedName(Name):
    def __init__(self, name, location, declared_at, module, mname=None):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname

    def __repr__(self):
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname)


class UndefinedName(str):
    def __repr__(self):
        return 'UndefinedName({})'.format(self)


class MultiName(object):
    def __init__(self, names):
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.names)
            else:
                allnames.append(n)
        self.names = list(set(allnames))

    def __repr__(self):
        return 'MultiName({})'.format(self.names)


class Fork(object):
    def __init__(self, extractor):
        self.extractor = extractor
        self.parent = extractor.flow
        self.forks = []
        self.first_flow = None

    def do(self, *blocks):
        e = self.extractor
        p = self.parent
        flow = None
        for nodes in blocks:
            if nodes:
                e.flow = e.add_flow(np(nodes[0]), [p])
                flow = flow or e.flow
                if not self.first_flow:
                    self.first_flow = e.flow
                for n in nodes: e.visit(n)
                p = e.flow

        self.forks.append(e.flow)
        return flow

    def empty(self):
        self.forks.append(self.parent)


class Scope(object):
    def __init__(self, parent):
        self.parent = parent
        self.locals = set()
        self.globals = set()


class FuncScope(Scope, Location):
    def __init__(self, parent, node, is_lambda=False):
        Scope.__init__(self, parent)
        self.args = []
        self.declared_at = np(node)
        if is_lambda:
            self.name = 'lambda'
            self.location = np(node.body)
        else:
            self.name = node.name
            self.location = np(node.body[0])

        for n in node.args.args:
            if PY2:
                self.args.append(ArgumentName(n.id, self.location, np(n), self))
            else:
                self.args.append(ArgumentName(n.arg, self.location, np(n), self))

        for n in (node.args.vararg, node.args.kwarg):
            if n:
                if PY2:
                    self.args.append(ArgumentName(n, self.location, self.location, self))
                else:
                    self.args.append(ArgumentName(n.arg, self.location, np(n), self))

        self.flow = Flow(self, self.location)
        for arg in self.args:
            self.flow.add_name(arg)


    @property
    def names(self):
        return self.last_flow.names

    def __repr__(self):
        return 'FuncScope({}, {})'.format(self.name, self.location)


class ClassScope(Scope, Location):
    def __init__(self, parent, node):
        Scope.__init__(self, parent)
        self.name = node.name
        self.declared_at = np(node)
        self.location = np(node.body[0])
        self.flow = Flow(self, self.location)

    @property
    def names(self):
        return self.parent.names


class Region(Location):
    def __init__(self, flow, start, end):
        self.flow = flow
        self.location = start
        self.end = end

    def __repr__(self):
        return 'Region({0.flow}, {0.location}, {0.end})'.format(self)


class BuiltinScope(object):
    @cached_property
    def names(self):
        names = {k: Name(k, (0, 0)) for k in dir(builtins)}
        names.update({k: Name(k, (0, 0))
                      for k in dir(compat)
                      if k.startswith('__')})
        return names


class SourceScope(Scope):
    def __init__(self, lines):
        Scope.__init__(self, BuiltinScope())
        self.lines = lines
        self.flows = defaultdict(list)
        self.allflows = []
        self.scope_flows = defaultdict(list)
        self.regions = []
        self._global_names = {}

    def get_level(self, loc, check_colon=False):
        l, c = loc
        try:
            line = self.lines[l - 1][:c]
        except IndexError:
            return c

        if len(line) < c:
            return c

        if check_colon:
            rsline = line.rstrip()
            if rsline.endswith(':'):
                return -1

        sline = line.lstrip()
        return len(line) - len(sline)

    def add_flow(self, flow, check_colon=False, level=None):
        if level is None:
            level = self.get_level(flow.location, check_colon)
        flow.level = level
        flow.top = self
        insert_loc(self.flows[level], flow)
        insert_loc(self.allflows, flow)
        insert_loc(self.scope_flows[flow.scope], flow)
        return flow

    def add_region(self, flow, start, end):
        region = Region(flow, start, end)
        insert_loc(self.regions, region)

    def add_global(self, name):
        self._global_names[name.name] = name

    @cached_property
    def names(self):
        names = self.flows[0][-1].names.copy()
        names.update(self._global_names)
        return names

    def flow_at(self, loc):
        flow = None
        lloc = Location(loc)

        idx = bisect(self.regions, lloc) - 1
        if idx >=0:
            region = self.regions[idx]
            if region.end > loc:
                flow = region.flow

        if not flow:
            flows = self.allflows
            level = self.get_level(loc)
            while True:
                idx = bisect(flows, lloc) - 1
                flow = flows[idx]
                if level < self.scope_flows[flow.scope][0].level:
                    flows = self.scope_flows[flow.scope.parent]
                else:
                    break

            flow_level = abs(flow.level - level)
            scope = flow.scope
            while idx >= 0:
                idx -= 1
                f = flows[idx]
                if f.scope != scope:
                    break

                flevel = abs(f.level - level)
                if flevel < flow_level:
                    flow = f
                    flow_level = flevel

        return flow

    def names_at(self, loc):
        flow = self.flow_at(loc)
        # print self.regions, flow, loc, self.get_level(loc), flow._names
        return flow.names_at(loc)

    @property
    def all_names(self):
        for flows in itervalues(self.flows):
            for flow in flows:
                for name in flow._names:
                    yield flow, name


class Flow(Location):
    def __init__(self, scope, location, parents=None):
        self.scope = scope
        self.location = location
        self.parents = parents or []
        self.level = None
        self._names = []

    def add_name(self, name):
        if name.name in self.scope.globals:
            self.top.add_global(name)
        else:
            self.scope.locals.add(name.name)
            insert_loc(self._names, name)

    @cached_property
    def names(self):
        names = self.parent_names.copy()
        names.update((name.name, name) for name in self._names)
        return names

    @cached_property
    def parent_names(self):
        parents = self.parents[:]
        if len(parents) == 1:
            return parents[0].names
        elif len(parents) > 1:
            names = {}

            nameset = set()
            for p in parents:
                nameset.update(p.names)

            for n in nameset:
                nrow = set(p.names.get(n, UndefinedName(n)) for p in parents)
                if len(nrow) == 1:
                    names[n] = list(nrow)[0]
                else:
                    names[n] = MultiName(list(nrow))

            return names
        else:
            if self.scope.parent:
                pnames = self.scope.parent.names
                outer_names = set(pnames).difference(self.scope.locals)
                return {n: pnames[n] for n in outer_names}
            else:
                return {}

    def names_at(self, loc):
        names = self.parent_names.copy()
        idx = bisect(self._names, Location(loc))
        names.update((name.name, name) for name in self._names[:idx])
        return names

    def loop(self):
        self.parents.append(LoopFlow(self))
        # cached_property.invalidate(self, 'names')
        # cached_property.invalidate(self, 'parent_names')
        return self

    def linkto(self, flow):
        self.parents.append(flow)
        # cached_property.invalidate(self, 'names')
        # cached_property.invalidate(self, 'parent_names')
        return self

    def __repr__(self):
        return '<Flow({location}, {level})>'.format(**vars(self))


class LoopFlow(object):
    def __init__(self, parent):
        self.parent = parent
        self._resolving = False

    @property
    def names(self):
        if self._resolving:
            return {}

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


class Extractor(NodeVisitor):
    def __init__(self, source):
        self.tree = source.tree
        self.top = SourceScope(source.lines)
        self.scope = self.top
        self.flow = self.add_flow((1, 0))

    def process(self):
        for node in self.tree.body:
            self.visit(node)

        return self.top

    @contextmanager
    def fork(self, node):
        f = Fork(self)
        yield f
        self.join(node, f.parent, f.forks)

    def add_flow(self, loc, parents=None, level=None):
        return self.top.add_flow(Flow(self.scope, loc, parents), level=level)

    def add_region(self, node, flow=None, end_node=None):
        self.top.add_region(flow or self.flow,
            np(node), get_expr_end(end_node or node))

    def join(self, node, parent, forks):
        last_line = get_expr_end(node)[0]
        loc = last_line + 1, parent.level
        self.flow = self.add_flow(loc, forks, parent.level)

    def shift(self, node, nodes):
        flow = self.flow
        self.flow = self.add_flow(np(nodes[0]), [flow])
        for n in nodes: self.visit(n)
        self.join(node, flow, [self.flow])

    def visit_Assign(self, node):
        eend = get_expr_end(node.value)
        for targets in node.targets:
            for name, idx in get_indexes_for_target(targets, [], []):
                if isinstance(name, UNSUPPORTED_ASSIGMENTS):
                    continue
                self.flow.add_name(AssignedName(name.id, eend, np(name), node.value))
        self.visit(node.value)

    def visit_If(self, node):
        self.visit(node.test)
        with self.fork(node) as fork:
            fork.do(node.body)
            if node.orelse:
                fork.do(node.orelse)
            else:
                fork.empty()

    def visit_For(self, node):
        with self.fork(node) as fork:
            fork.empty()
            fork.do(node.body)
            for nn, _idx in get_indexes_for_target(node.target, [], []):
                fork.first_flow.add_name(
                    AssignedName(nn.id, np(node.body[0]), np(nn), node.iter))

            fork.first_flow.linkto(LoopFlow(self.flow))

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_While(self, node):
        self.visit(node.test)
        with self.fork(node) as fork:
            fork.empty()
            fork.do(node.body)
            fork.first_flow.linkto(LoopFlow(self.flow))

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_Import(self, node):
        loc = get_expr_end(node)
        for a in node.names:
            name = a.asname or a.name.partition('.')[0]
            self.flow.add_name(ImportedName(name, loc, np(node), a.name, None))

    def visit_ImportFrom(self, node):
        loc = get_expr_end(node)
        for a in node.names:
            name = a.asname or a.name
            module = '.' * node.level + (node.module or '')
            self.flow.add_name(ImportedName(name, loc, np(node), module, a.name))

    def visit_TryExcept(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                flow = fork.do(h.body)
                if h.name:
                    nn = h.name
                    flow.add_name(AssignedName(nn.id, np(h.body[0]), np(nn), h.type))

    def visit_Try(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                flow = fork.do(h.body)
                if h.name:
                    flow.add_name(AssignedName(h.name, np(h.body[0]), np(h), h.type))

    @contextmanager
    def nest(self):
        scope = self.scope
        flow = self.flow
        yield scope, flow
        self.scope = scope
        self.flow = flow

    def visit_FunctionDef(self, node):
        with self.nest() as (_, flow):
            self.scope = FuncScope(self.scope, node)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body: self.visit(n)
            self.scope.last_flow = self.flow

    def visit_Lambda(self, node):
        with self.nest() as (_, flow):
            self.scope = FuncScope(self.scope, node, True)
            self.flow = self.top.add_flow(self.scope.flow, level=-1)
            self.add_region(node.body)
            self.visit(node.body)

    def visit_ClassDef(self, node):
        with self.nest() as (_, flow):
            self.scope = ClassScope(self.scope, node)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body: self.visit(n)

    def visit_Expr(self, node):
        self.add_region(node)
        self.generic_visit(node)

    def visit_ListComp(self, node):
        for g in node.generators:
            for nn, _idx in get_indexes_for_target(g.target, [], []):
                self.flow.add_name(AssignedName(nn.id, np(node), np(nn), g.iter))

    visit_GeneratorExp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_SetComp = visit_ListComp

    def visit_With(self, node):
        if PY2:
            items = [node]
        else:
            items = node.items

        for it in items:
            if it.optional_vars:
                for nn, _idx in get_indexes_for_target(it.optional_vars, [], []):
                    self.flow.add_name(AssignedName(nn.id, np(node.body[0]), np(nn), node))

        self.generic_visit(node)

    def visit_Global(self, node):
        self.scope.globals.update(node.names)
