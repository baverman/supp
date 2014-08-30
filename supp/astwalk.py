from __future__ import print_function

from ast import NodeVisitor, iter_child_nodes, iter_fields, Store
from contextlib import contextmanager

from .compat import iteritems, string_types
from .util import Location

LW = '   '


def dumptree(node, result, level):
    fields = [(k, v) for k, v in iter_fields(node)
        if (hasattr(v, '_fields') and not isinstance(v, Store))
            or (isinstance(v, list) and v and hasattr(v[0], '_fields'))]
    field_names = set(k for k, v in fields)

    result.append('{} {} {}'.format(LW * level, type(node).__name__,
        ', '.join('{}: {}'.format(k, v) for k, v in sorted(iteritems(vars(node)))
            if k not in field_names)))

    for k, v in fields:
        if isinstance(v, list):
            result.append('{} {}:'.format(LW * (level + 1), k))
            for child in v:
                dumptree(child, result, level + 2)
        else:
            result.append('{} {}:'.format(LW * (level + 1), k))
            dumptree(v, result, level + 2)

    return result


def dump(node):
    return '\n'.join(dumptree(node, [], 0))


def print_dump(node):
    print(dump(node))


class GetExprEnd(NodeVisitor):
    def __call__(self, node):
        self.last_loc = node.lineno, node.col_offset + 1
        self.visit(node)
        return self.last_loc

    def visit_Store(self, node):
        pass

    def visit_Load(self, node):
        pass

    def __getattr__(self, name):
        def inner(node):
            try:
                self.last_loc = node.lineno, node.col_offset + 1
            except AttributeError:
                pass
            self.generic_visit(node)

        setattr(self, name, inner)
        return inner


def np(node):
    return node.lineno, node.col_offset


class Name(Location):
    def __init__(self, name, location=None):
        self.name = name
        self.location = location or declared_at

    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__,
            self.name, self.location)


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


class Extractor(NodeVisitor):
    def __init__(self, scope, flow, tree):
        self.scope = scope
        self.lines = scope.lines
        self.flow = flow
        self.tree = tree
        self.get_expr_end = GetExprEnd()

    def process(self):
        # print_dump(self.tree)
        for node in self.tree.body:
            self.visit(node)

    @contextmanager
    def fork(self, node):
        f = Fork(self)
        yield f
        self.join(node, f.parent, f.forks)

    def join(self, node, parent, forks):
        last_line = self.get_expr_end(node)[0]
        loc = last_line + 1, parent.location[1]
        self.flow = self.scope.add_flow(loc, forks)

    def shift(self, node, nodes):
        flow = self.flow
        self.flow = self.scope.add_flow(np(nodes[0]), [flow])
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


class Fork(object):
    def __init__(self, extractor):
        self.extractor = extractor
        self.scope = extractor.scope
        self.parent = extractor.flow
        self.forks = []

    def do(self, nodes, loop=False):
        e = self.extractor
        e.flow = self.scope.add_flow(np(nodes[0]), [self.parent])
        for n in nodes: e.visit(n)
        self.forks.append(e.flow)
        return e.flow

    def empty(self):
        self.forks.append(self.parent)
