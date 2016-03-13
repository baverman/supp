from ast import Name

from .util import np
from .astwalk import ImportedName, AssignedName


def evaluate(project, scope, node):
    node_type = type(node)
    if node_type is Name:
        names = scope.names_at(np(node))
        name = names.get(node.id)
        if name:
            return evaluate(project, scope, name)
    elif node_type is AssignedName:
        return evaluate(project, scope, node.value_node)
    elif node_type is ImportedName:
        return evaluate(project, node.scope, node.resolve(project))
    elif getattr(node, 'names', None):
        return node
