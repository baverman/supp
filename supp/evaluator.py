from __future__ import print_function
import logging
from ast import Name as AstName, Attribute, Str, Call, AST

from .util import np
from .name import (ImportedName, MultiName, MultiValue, Object,
                   RuntimeName, Resolvable, AssignedName, Callable,
                   CompositeValue)

log = logging.getLogger('supp.evaluator')

try:
    from ast import Constant
except ImportError:
    class Constant: pass  # type: ignore[no-redef]

try:
    from ast import Bytes
except ImportError:
    class Bytes: pass  # type: ignore[no-redef]

if False:
    import typing as t
    from .project import Project
    from .name import Name


class EvalCtx(object):
    def __init__(self, project):
        # type: (Project) -> None
        self.project = project
        self.level = 0
        self.nodes = set()  # type: set[t.Hashable]

    def evaluate(self, node):
        # type: (AST | Object | Name | None) -> Object | None
        if node is None or node in self.nodes:
            return None
        self.nodes.add(node)
        self.level += 1
        result = self._evaluate(node)  # type: ignore[no-untyped-call]
        self.level -= 1
        self.nodes.remove(node)
        return result  # type: ignore[no-any-return]

    def _evaluate(self, node):  # type: ignore[no-untyped-def]
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
                return self.evaluate(value.get_attr(self, node.attr))
        elif node_type is MultiName:
            values = []
            for n in node.valid_names:
                v = self.evaluate(n)
                if v:
                    values.append(v)
            return CompositeValue(values)
        elif node_type is Call:
            func = self.evaluate(node.func)
            if func:
                if isinstance(func, Callable):
                    return func.call(self)  # type: ignore[attr-defined]
                else:
                    log.warn('Non-callable %r %r', type(func), func)
        elif isinstance(node, Resolvable):
            return node.resolve(self)  # type: ignore[attr-defined]
        elif isinstance(node, Object):
            return node
        elif node_type is Str:
            return RuntimeName('__none__', node.s)
        elif node_type is Bytes:
            return RuntimeName('__none__', node.s)
        elif node_type is Constant:
            return RuntimeName('__none__', node.value)
        elif isinstance(node, Callable):
            return node
        else:
            log.warn('Unknown node type %r %r', node_type, node)

    def declarations(self, node, result=[]):
        # type: (Name | AstName | MultiName | MultiValue | Attribute | ImportedName, list[Name]) -> list[Name]
        node_type = type(node)
        cname = None
        if node_type is AstName:
            ast_name = node  # type: AstName # type: ignore[assignment]
            names = ast_name.flow.names_at(np(ast_name))  # type: ignore[attr-defined]
            cname = names.get(ast_name.id)
        elif node_type is MultiName:
            mname = node  # type: MultiName # type: ignore[assignment]
            names = mname.valid_names
            if names:
                if len(names) > 1:
                    result.append(names)
                else:
                    cname = names[0]
        elif node_type is MultiValue:
            mvalue = node  # type: MultiValue # type: ignore[assignment]
            names = []
            for n in mvalue.values:
                names.append(n)

            if names:
                if len(names) > 1:
                    result.append(names)
                else:
                    cname = names[0]
        elif node_type is Attribute:
            ast_attr = node  # type: Attribute # type: ignore[assignment]
            value = self.evaluate(ast_attr.value)
            if value:
                cname = value.get_attr(self, ast_attr.attr)
        elif node_type is ImportedName:
            iname = node  # type: ImportedName # type: ignore[assignment]
            result.append(iname)
            cname = iname.resolve(self)
        else:
            result.append(node)  # type: ignore[arg-type]

        if cname:
            return self.declarations(cname, result)

        return result
