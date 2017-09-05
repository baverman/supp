import logging
from ast import Name as AstName, Attribute, Str, Call

from .util import np
from .name import (ImportedName, MultiName, UndefinedName, MultiValue, Object,
                   RuntimeName, Resolvable, AssignedName, AdditionalNameWrapper,
                   Callable)

log = logging.getLogger('supp.evaluator')


class EvalCtx(object):
    def __init__(self, project, scope):
        self.project = project
        self.scope = scope

    def evaluate(self, node):
        node_type = type(node)
        if node_type is AstName:
            names = node.flow.names_at(np(node))
            name = names.get(node.id)
            if name:
                return self.evaluate(name)
        elif node_type is AssignedName:
            return self.evaluate(node.value_node)
        elif node_type is ImportedName:
            return self.evaluate(node.resolve(self))
        elif node_type is Attribute:
            value = self.evaluate(node.value)
            if value:
                return self.evaluate(value.attrs.get(node.attr))
        elif node_type is MultiName:
            names = {}
            for n in node.alt_names:
                if type(n) is not UndefinedName:
                    v = self.evaluate(n)
                    if v:
                        names.update(v.attrs)
            return AdditionalNameWrapper(None, names)
        elif node_type is Call:
            func = self.evaluate(node.func)
            if func:
                if isinstance(func, Callable):
                    return func.call(self)
                else:
                    log.warn('Non-callable %r %r', type(func), func)
        elif isinstance(node, Resolvable):
            return node.resolve(self)
        elif isinstance(node, Object):
            return node
        elif node_type is Str:
            return RuntimeName('__none__', node.s)
        else:
            log.warn('Unknown node type %r %r', node_type, node)


def declarations(project, scope, node, result=[]):
    node_type = type(node)
    cname = None
    if node_type is AstName:
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
    elif node_type is MultiValue:
        names = []
        for n in node.values:
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
