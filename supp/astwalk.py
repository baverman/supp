from __future__ import print_function

from ast import NodeVisitor, iter_child_nodes, iter_fields, Store

from .compat import iteritems

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


class Name(object):
    def __init__(self, name, declared_at):
        self.name = name
        self.declared_at = declared_at

    def __lt__(self, other):
        return self.declared_at < other.declared_at

    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__, self.name, self.declared_at)


class AssignedName(Name):
    def __init__(self, name, declared_at, value_node):
        Name.__init__(self, name, declared_at)
        self.value_node = value_node


class Extractor(NodeVisitor):
    def __init__(self, scope, tree):
        self.scope = scope
        self.tree = tree

        self.get_expr_end = GetExprEnd()

    def process(self):
        print_dump(self.tree)
        for node in self.tree.body:
            self.visit(node)

    def visit_Assign(self, node):
        nn = node.targets[0]
        self.scope.add_name(AssignedName(nn.id, np(nn), node.value))
