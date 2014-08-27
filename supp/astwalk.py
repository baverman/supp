from __future__ import print_function

from ast import NodeVisitor, iter_child_nodes, iter_fields, Store
from contextlib import contextmanager

from .compat import iteritems, string_types
from .util import Loc

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
            self.last_loc = node.lineno, node.col_offset + 1
            self.generic_visit(node)

        setattr(self, name, inner)
        return inner


def np(node):
    return node.lineno, node.col_offset


class Name(Loc):
    def __init__(self, name, declared_at):
        self.name = name
        self.declared_at = declared_at

    def __repr__(self):
        return '{}({}, {})'.format(
            self.__class__.__name__, self.name, self.declared_at)


class AssignedName(Name):
    def __init__(self, name, declared_at, value_node):
        Name.__init__(self, name, declared_at)
        self.value_node = value_node


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
        self.flow = flow
        self.tree = tree
        self.get_expr_end = GetExprEnd()

    def process(self):
        # print_dump(self.tree)
        for node in self.tree.body:
            self.visit(node)

    @contextmanager
    def fork(self):
        f = Fork(self.scope, self.flow)
        yield f
        loc = f.last_line + 1, f.parent.declared_at[1]
        self.flow = self.scope.add_flow(loc, f.forks)

    def visit_Assign(self, node):
        nn = node.targets[0]
        self.flow.add_name(AssignedName(nn.id, np(nn), node.value))

    def visit_If(self, node):
        self.visit(node.test)
        with self.fork() as fork:
            self.flow = fork.add_flow(np(node.body[0]))
            for r in node.body:
                self.visit(r)
            fork.forks.append(self.flow)

            self.flow = fork.add_flow(np(node.orelse[0]))
            for r in node.orelse:
                self.visit(r)
            fork.forks.append(self.flow)

            fork.last_line = self.get_expr_end(node)[0]


class Fork(object):
    def __init__(self, scope, parent):
        self.scope = scope
        self.parent = parent
        self.forks = []

    def add_flow(self, declared_at):
        return self.scope.add_flow(declared_at, [self.parent])
