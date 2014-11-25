from bisect import bisect
from collections import defaultdict
from contextlib import contextmanager
from ast import NodeVisitor

from .util import Location, np, GetExprEnd, insert_loc, cached_property
from .compat import PY2


class Name(Location):
    def __init__(self, name, location=None):
        self.name = name
        self.location = location

    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__,
            self.name, self.location)


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


class UndefinedName(str): pass


class MultiName(object):
    def __init__(self, names):
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.names)
            else:
                allnames.append(n)
        self.names = list(set(allnames))


class Fork(object):
    def __init__(self, extractor):
        self.extractor = extractor
        self.parent = extractor.flow
        self.forks = []

    def do(self, *blocks):
        e = self.extractor
        p = self.parent
        for nodes in blocks:
            if nodes:
                e.flow = e.add_flow(np(nodes[0]), [p])
                for n in nodes: e.visit(n)
                p = e.flow

        self.forks.append(e.flow)
        return e.flow

    def empty(self):
        self.forks.append(self.parent)


class Scope(object):
    def __init__(self, parent):
        self.parent = parent
        self.locals = set()


class FuncScope(Scope):
    def __init__(self, parent, node):
        Scope.__init__(self, parent)
        self.name = node.name
        self.args = []
        self.declared_at = np(node)
        self.location = np(node.body[0])

        for n in node.args.args:
            if PY2:
                self.args.append(ArgumentName(n.id, self.location, np(n), self))
            else:
                self.args.append(ArgumentName(n.arg, self.location, np(n), self))

        self.flow = Flow(self, self.location)
        for arg in self.args:
            self.flow.add_name(arg)


class ClassScope(Scope):
    def __init__(self, parent, node):
        Scope.__init__(self, parent)
        self.name = node.name
        self.declared_at = np(node)
        self.location = np(node.body[0])
        self.flow = Flow(self, self.location)

    @property
    def names(self):
        return self.parent.names


class SourceScope(Scope):
    def __init__(self, lines):
        Scope.__init__(self, None)
        self.lines = lines
        self.flows = defaultdict(list)

    def get_level(self, loc):
        l, c = loc
        line = self.lines[l - 1][:c]
        sline = line.lstrip()
        return len(line) - len(sline)

    def get_level_flows(self, level):
        try:
            return self.flows[level]
        except KeyError:
            pass

        levels = sorted(self.flows)
        return self.flows[levels[bisect(levels, level) - 1]]

    def add_flow(self, flow):
        insert_loc(self.flows[self.get_level(flow.location)], flow)
        return flow

    @property
    def names(self):
        return self.flows[0][-1].names

    def names_at(self, loc):
        flows = self.get_level_flows(self.get_level(loc))
        idx = bisect(flows, Location(loc)) - 1
        return flows[idx].names_at(loc)


class Flow(Location):
    def __init__(self, scope, location, parents=None):
        self.scope = scope
        self.location = location
        self.parents = parents or []
        self._names = []

    def add_name(self, name):
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
        return self

    def linkto(self, flow):
        self.parents.append(flow)
        return self

    def __repr__(self):
        return '<Flow({})>'.format(self.location)


class LoopFlow(object):
    def __init__(self, parent):
        self._names = parent._names

    @cached_property
    def names(self):
        return {n.name: n for n in self._names}


class Extractor(NodeVisitor):
    def __init__(self, source):
        self.tree = source.tree
        self.get_expr_end = GetExprEnd()
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

    def add_flow(self, loc, parents=None):
        return self.top.add_flow(Flow(self.scope, loc, parents))

    def join(self, node, parent, forks):
        last_line = self.get_expr_end(node)[0]
        loc = last_line + 1, parent.location[1]
        self.flow = self.add_flow(loc, forks)

    def shift(self, node, nodes):
        flow = self.flow
        self.flow = self.add_flow(np(nodes[0]), [flow])
        for n in nodes: self.visit(n)
        self.join(node, flow, [self.flow])

    def visit_Assign(self, node):
        nn = node.targets[0]
        self.flow.add_name(AssignedName(nn.id, self.get_expr_end(node.value),
            np(nn), node.value))

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
            fork.do(node.body).loop()
            nn = node.target
            self.flow.add_name(
                AssignedName(nn.id, np(node.body[0]), np(nn), node.iter))

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_While(self, node):
        self.visit(node.test)
        with self.fork(node) as fork:
            fork.empty()
            fork.do(node.body).loop()

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_Import(self, node):
        loc = self.get_expr_end(node)
        for a in node.names:
            name = a.asname or a.name.partition('.')[0]
            self.flow.add_name(ImportedName(name, loc, np(node), a.name, None))

    def visit_ImportFrom(self, node):
        loc = self.get_expr_end(node)
        for a in node.names:
            name = a.asname or a.name
            module = '.' * node.level + (node.module or '')
            self.flow.add_name(ImportedName(name, loc, np(node), module, a.name))

    def visit_TryExcept(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                fork.do(h.body)
                if h.name:
                    nn = h.name
                    self.flow.add_name(
                        AssignedName(nn.id, np(h.body[0]), np(nn), h.type))

    def visit_Try(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                fork.do(h.body)
                if h.name:
                    self.flow.add_name(
                        AssignedName(h.name, np(h.body[0]), np(h), h.type))

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
            self.flow = self.top.add_flow(self.scope.flow)
            for n in node.body: self.visit(n)

    def visit_ClassDef(self, node):
        with self.nest() as (_, flow):
            self.scope = ClassScope(self.scope, node)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow)
            for n in node.body: self.visit(n)
