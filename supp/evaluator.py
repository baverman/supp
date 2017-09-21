from __future__ import print_function
import logging
from ast import Name as AstName, Attribute, Str, Call

from .util import np
from .name import (ImportedName, MultiName, UndefinedName, MultiValue, Object,
                   RuntimeName, Resolvable, AssignedName, AdditionalNameWrapper,
                   Callable)

log = logging.getLogger('supp.evaluator')


class EvalCtx(object):
    def __init__(self, project):
        self.project = project
        self.level = 0
        self.nodes = set()

    def evaluate(self, node):
        if node in self.nodes:
            return None
        self.nodes.add(node)
        self.level += 1
        result = self._evaluate(node)
        self.level -= 1
        self.nodes.remove(node)
        return result

    def _evaluate(self, node):
        node_type = type(node)

        # if hasattr(node, 'scope'):
        #     print('^^^' + '  '*self.level, node_type, node, node.scope.filename)
        # elif isinstance(node, AstName):
        #     print('^^^' + '  '*self.level, node_type, node.id, np(node), node.flow.scope.filename)
        # else:
        #     print('^^^' + '  '*self.level, node_type, node)

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
        elif isinstance(node, Callable):
            return node
        else:
            log.warn('Unknown node type %r %r', node_type, node)

    def declarations(self, node, result=[]):
        node_type = type(node)
        cname = None
        if node_type is AstName:
            names = node.flow.names_at(np(node))
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
            value = self.evaluate(node.value)
            if value:
                cname = value.attrs.get(node.attr)
        elif node_type is ImportedName:
            result.append(node)
            cname = node.resolve(self)
        else:
            result.append(node)

        if cname:
            return self.declarations(cname, result)

        return result
