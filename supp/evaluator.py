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
                v = evaluate(project, n.scope.top, n)
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
    elif hasattr(node, 'names'):
        return node


def declarations(project, scope, node, result=[]):
    node_type = type(node)
    cname = None
    if node_type is Name:
        names = scope.names_at(np(node))
        cname = names.get(node.id)
    elif node_type is MultiName:
        names = []
        for n in node.alt_names:
            if type(n) is not UndefinedName:
                names.append(n)

        if names:
            if len(names) > 1:
                result.append(names)
            else:
                cname = names[0]
    elif node_type is Attribute:
        value = evaluate(project, scope, node.value)
        if value:
            cname = value.names.get(node.attr)
    elif node_type is ImportedName:
        result.append(node)
        cname = node.resolve(project)
    else:
        result.append(node)

    if cname:
        return declarations(project, None, cname, result)

    return result
