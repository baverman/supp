from __future__ import print_function
from contextlib import contextmanager
from ast import Attribute, Subscript

from .compat import PY2
from .name import ImportedName, AssignedName
from .scope import SourceScope, Flow, LoopFlow, ClassScope, FuncScope
from .util import np, get_expr_end, get_indexes_for_target, visitor

if PY2:
    UNSUPPORTED_ASSIGMENTS = Subscript
else:
    from ast import Starred
    UNSUPPORTED_ASSIGMENTS = Subscript, Starred


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
                for n in nodes:
                    e.visit(n)
                p = e.flow

        self.forks.append(e.flow)
        return flow

    def empty(self):
        self.forks.append(self.parent)


@visitor
class extract(object):
    def process(self, tree, scope):
        self.scope = self.top = scope
        self.flow = self.add_flow((1, 0))

        for node in tree.body:
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
        # print node, end_node, np(node), get_expr_end(end_node or node)
        self.top.add_region(flow or self.flow,
                            np(node),
                            get_expr_end(end_node or node))

    def join(self, node, parent, forks):
        last_line = get_expr_end(node)[0]
        loc = last_line + 1, -parent.level
        self.flow = self.add_flow(loc, forks, parent.level)

    def shift(self, node, nodes):
        flow = self.flow
        self.flow = self.add_flow(np(nodes[0]), [flow])
        for n in nodes:
            self.visit(n)
        self.join(node, flow, [self.flow])

    def visit_Assign(self, node):
        eend = get_expr_end(node.value)
        for targets in node.targets:
            for name, _ in get_indexes_for_target(targets, [], []):
                if isinstance(name, Attribute):
                    self.top.add_attr_assign(self.scope, name, node.value)
                elif isinstance(name, UNSUPPORTED_ASSIGMENTS):
                    continue
                else:
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

            self.visit(node.iter)
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
        start = np(node)
        for a in node.names:
            if a.asname:
                name = a.asname
                iname = a.name
            else:
                name = a.name.partition('.')[0]
                iname = name
                self.top._imports.append(a.name)

            declared_at = self.top.find_id_loc(name, start)
            self.flow.add_name(ImportedName(name, loc, declared_at, iname, None))

    def visit_ImportFrom(self, node):
        loc = get_expr_end(node)
        start = np(node)
        for a in node.names:
            name = a.asname or a.name
            declared_at = self.top.find_id_loc(name, start)
            module = '.' * node.level + (node.module or '')
            if name == '*':
                self.top._star_imports.append((loc, declared_at, module, self.flow))
            else:
                self.flow.add_name(ImportedName(name, loc, declared_at, module, a.name))

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
        for d in node.decorator_list:
            self.visit(d)
        with self.nest() as (_, flow):
            self.scope = FuncScope(self.scope, node, top=self.top)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body:
                self.visit(n)
            self.scope.last_flow = self.flow

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node):
        with self.nest():
            self.scope = FuncScope(self.scope, node, True, top=self.top)
            self.flow = self.top.add_flow(self.scope.flow, level=-1)
            self.add_region(node.body)
            self.visit(node.body)

    def visit_ClassDef(self, node):
        with self.nest() as (_, flow):
            self.scope = ClassScope(self.scope, node, top=self.top)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body:
                self.visit(n)
            self.scope.last_flow = self.flow

    def visit_expr(self, node):
        self.add_region(node)
        self.generic_visit(node)

    visit_Expr = visit_expr
    visit_Dict = visit_expr
    visit_Set = visit_expr
    visit_List = visit_expr
    visit_Tuple = visit_expr

    def visit_ListComp(self, node):
        flow = self.flow
        for g in node.generators:
            self.add_region(g.iter)
            self.visit(g.iter)
            self.flow = self.add_flow(np(g.target), [self.flow], -1)
            for nn, _idx in get_indexes_for_target(g.target, [], []):
                self.flow.add_name(AssignedName(nn.id, np(node), np(nn), g.iter))
            if g.ifs:
                self.add_region(g.ifs[0], end_node=g.ifs[-1])
                for inode in g.ifs:
                    self.visit(inode)

        elt = getattr(node, 'elt', None) or node.value
        self.add_region(node, end_node=elt)
        self.visit(elt)
        self.flow = flow

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


def extract_scope(project, source):
    scope = extract(source.tree,
                    SourceScope(project, source.lines, source.filename))
    scope.resolve_star_imports()
    return scope
