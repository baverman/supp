from ast import Name, Attribute

from .util import np
from .name import ImportedName, MultiName, UndefinedName


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
        value = scope.evaluate(node.value)
        if value:
            cname = value.attrs.get(node.attr)
    elif node_type is ImportedName:
        result.append(node)
        cname = node.resolve()
    else:
        result.append(node)

    if cname:
        return declarations(project, None, cname, result)

    return result
