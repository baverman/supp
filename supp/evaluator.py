from ast import Name, Attribute

from .util import np
from .name import (ImportedName, AssignedName, MultiName, AdditionalNameWrapper,
                   UndefinedName)


def evaluate(project, scope, node):
    node_type = type(node)
    if node_type is Name:
        names = scope.names_at(np(node))
        name = names.get(node.id)
        if name:
            return evaluate(project, scope, name)
    elif node_type is MultiName:
        names = {}
        for n in node.alt_names:
            if type(n) is not UndefinedName:
                v = evaluate(project, n.scope, n)
                if v:
                    names.update(v.names)
        return AdditionalNameWrapper(None, names)
    elif node_type is Attribute:
        value = evaluate(project, scope, node.value)
        if value:
            return evaluate(project, scope, value.names.get(node.attr))
    elif node_type is AssignedName:
        return evaluate(project, scope, node.value_node)
    elif node_type is ImportedName:
        return evaluate(project, node.scope, node.resolve(project))
    elif getattr(node, 'names', None):
        return node
