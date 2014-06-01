from __future__ import print_function

from ast import NodeVisitor, iter_child_nodes, iter_fields, Store

from .compat import iteritems

LW = '   '

def dump(node, level=0):
    fields = [(k, v) for k, v in iter_fields(node)
        if (hasattr(v, '_fields') and not isinstance(v, Store))
            or (isinstance(v, list) and v and hasattr(v[0], '_fields'))]
    field_names = set(k for k, v in fields)

    print(LW * level, type(node).__name__, ', '.join('{}: {}'.format(k, v)
        for k, v in sorted(iteritems(vars(node))) if k not in field_names))

    for k, v in fields:
        if isinstance(v, list):
            print(LW * (level + 1), k + ':')
            for child in v:
                dump(child, level + 2)
        else:
            print(LW * (level + 1), k + ':')
            dump(v, level + 2)


class NameExtractor(NodeVisitor):
    def __init__(self, scope, tree):
        self.scope = scope
        self.tree = tree

    def process(self):
        # print(dump(self.tree))
        dump(self.tree)
        self.visit(self.tree)
