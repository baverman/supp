from __future__ import annotations

import dataclasses
import logging
import typing as t
from ast import AST, Attribute, BinOp, Call, Subscript
from ast import Name as AstName

from .ast_types import Annotation
from .compat import HAS_CONSTANTS
from .module import SourceModule
from .name import (
    AnnotatedWrapper,
    AssignedName,
    Callable,
    ClassObject,
    CompositeValue,
    FuncObject,
    ImportedName,
    InstanceValue,
    MultiName,
    MultiValue,
    Object,
    Resolvable,
    RuntimeName,
)
from .util import np

log = logging.getLogger('supp.evaluator')

if HAS_CONSTANTS:
    from ast import Constant

    class Str:
        pass

    class Bytes:
        pass
else:
    from ast import Bytes, Str  # type: ignore[assignment]

    class Constant:  # type: ignore[no-redef]
        pass


if t.TYPE_CHECKING:
    from .name import Name
    from .project import Project
    from .scope import Flow


_TYPING_MODULES = 'typing', 'typing_extensions'


@dataclasses.dataclass
class AnnotationEvalResult:
    type: Object | None
    is_class_var: bool


class EvalCtx(object):
    def __init__(self, project: Project) -> None:
        self.project = project
        self.level = 0
        self.nodes: set[t.Hashable] = set()

    def evaluate(self, node: AST | Object | Name | MultiName | None) -> Object | None:
        if node is None or node in self.nodes:
            return None
        self.nodes.add(node)
        self.level += 1
        result = self._evaluate(node)  # type: ignore[no-untyped-call]
        self.level -= 1
        self.nodes.remove(node)
        return result  # type: ignore[no-any-return]

    def annotation_context(
        self,
        flow: Flow,
        substitutions: dict[str, Object] | None = None,
    ) -> EvalAnnotationCtx:
        return EvalAnnotationCtx(self.project, flow, substitutions)

    def evaluate_annotation(
        self,
        annotation: Annotation,
        substitutions: dict[str, Object] | None = None,
    ) -> AnnotationEvalResult:
        obj = self.annotation_context(annotation.flow, substitutions).evaluate(annotation)

        result = AnnotationEvalResult(None, False)
        if obj is None:
            return result

        if type(obj) is ClassVarWrapper:
            obj = obj.object
            result.is_class_var = True

        if type(obj) is CompositeValue:
            values = obj.values
        else:
            values = [obj]

        rvalues: list[Object | None] = []
        for it in values:
            if type(it) is TypeWrapper:
                rvalues.append(it.object)
            elif isinstance(it, Callable):
                rvalues.append(it.call(self))

        if len(rvalues) > 1:
            result.type = CompositeValue([it for it in rvalues if it is not None])
        elif rvalues:
            result.type = rvalues[0]

        return result

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
            if node.annotation:
                return self.evaluate_annotation(node.annotation).type
            return self.evaluate(node.value_node)
        elif node_type is ImportedName:
            return self.evaluate(node.resolve(self))
        elif node_type is Attribute:
            value = self.evaluate(node.value)
            if value:
                return self.evaluate(value.get_attr(self, node.attr))
        elif node_type is Subscript:
            value = self.evaluate(node.value)
            if isinstance(value, ClassObject):
                if hasattr(node.slice, 'elts'):
                    args_nodes = node.slice.elts
                else:
                    args_nodes = [node.slice]
                args = []
                for arg in args_nodes:
                    obj = self.evaluate(arg)
                    if obj is not None:
                        args.append(obj)
                return value.with_type_args(args)
            return value
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
                if type(func) is FuncObject and type(node.func) is Attribute:
                    owner = self.evaluate(node.func.value)
                    if isinstance(owner, (ClassObject, InstanceValue)) and owner.substitutions:
                        func = func.with_substitutions(owner.substitutions)
                if isinstance(func, Callable):
                    return func.call(self)
                else:
                    log.warning('Non-callable %r %r', type(func), func)
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
            log.warning('Unknown node type %r %r', node_type, node)

    def declarations(
        self,
        node: Name | AstName | MultiName | MultiValue | Attribute | ImportedName,
        result: list[list[Name]],
    ) -> list[list[Name]]:
        node_type = type(node)
        cname = None
        if node_type is AstName:
            ast_name: AstName = node  # type: ignore[assignment]
            names = ast_name.flow.names_at(np(ast_name))  # type: ignore[attr-defined]
            cname = names.get(ast_name.id)
        elif node_type is AnnotatedWrapper:
            awname: AnnotatedWrapper = node  # type: ignore[assignment]
            cname = awname.object
        elif node_type is MultiName:
            mname: MultiName = node  # type: ignore[assignment]
            names = mname.valid_names
            if names:
                if len(names) > 1:
                    result.append(names)
                else:
                    cname = names[0]
        elif node_type is MultiValue:
            mvalue: MultiValue = node  # type: ignore[assignment]
            names = []
            for n in mvalue.values:
                names.append(n)

            if names:
                if len(names) > 1:
                    result.append(names)
                else:
                    cname = names[0]
        elif node_type is Attribute:
            ast_attr: Attribute = node  # type: ignore[assignment]
            value = self.evaluate(ast_attr.value)
            if value:
                cname = value.get_attr(self, ast_attr.attr)
        elif node_type is ImportedName:
            iname: ImportedName = node  # type: ignore[assignment]
            result.append([iname])
            cname = iname.resolve(self)
        else:
            result.append([node])  # type: ignore[list-item]

        if cname:
            return self.declarations(cname, result)

        return result


class MarkerObject(Object):
    def __init__(self, typ: str) -> None:
        self.type = typ

    def __repr__(self) -> str:
        return f'MarkerObject({self.type!r})'


class TypeWrapper(Object):
    def __init__(self, obj: Object) -> None:
        self.object = obj

    def __repr__(self) -> str:
        return f'Type({self.object})'


class ClassVarWrapper(Object):
    def __init__(self, obj: Object) -> None:
        self.object = obj

    def __repr__(self) -> str:
        return f'ClassVar({self.object})'


class EvalAnnotationCtx(EvalCtx):
    def __init__(
        self,
        project: Project,
        flow: Flow,
        substitutions: dict[str, Object] | None = None,
    ) -> None:
        super().__init__(project)
        self.flow = flow
        self.substitutions = substitutions or {}

    def _evaluate(self, node):  # type: ignore[no-untyped-def]
        node_type = type(node)
        # print('@@', node)
        if node_type is AstName:
            if node.id in self.substitutions:
                return self.substitutions[node.id]
            names = node.flow.names_at(np(node))
            name = names.get(node.id)
            if not name:
                name = node.flow.names.get(node.id)
            if name:
                return self.evaluate(name)
        elif node_type is AssignedName:
            return self.annotation_context(node.scope.flow, self.substitutions).evaluate(
                node.value_node
            )
        elif node_type is ImportedName:
            if node.module in _TYPING_MODULES and node.mname:
                return MarkerObject(node.mname)
            return self.evaluate(node.resolve(self))
        elif isinstance(node, Resolvable):
            return node.resolve(self)  # type: ignore[attr-defined]
        elif isinstance(node, Object):
            return node
        elif node_type is Subscript:
            obj = self.evaluate(node.value)
            obj_type = type(obj)
            # print('!!', obj)
            if obj_type is MarkerObject:
                if obj.type == 'Union':  # type: ignore[union-attr]
                    if hasattr(node.slice, 'elts'):
                        return self.make_composite(node.slice.elts)
                    else:
                        return self.make_composite([node.slice])
                elif obj.type == 'Optional':  # type: ignore[union-attr]
                    return self.evaluate(node.slice)
                elif obj.type == 'Type':  # type: ignore[union-attr]
                    o = self.evaluate(node.slice)
                    if o is not None:
                        return TypeWrapper(o)
                elif obj.type == 'ClassVar':  # type: ignore[union-attr]
                    o = self.evaluate(node.slice)
                    if o is not None:
                        return ClassVarWrapper(o)
            else:
                if isinstance(obj, ClassObject):
                    if hasattr(node.slice, 'elts'):
                        args_nodes = node.slice.elts
                    else:
                        args_nodes = [node.slice]
                    args = []
                    for arg in args_nodes:
                        o = self.evaluate(arg)
                        if o is not None:
                            args.append(o)
                    return obj.with_type_args(args)
                return obj
        elif node_type is MultiName:
            return self.make_composite(node.valid_names)
        elif node_type is BinOp:
            return self.make_composite([node.left, node.right])
        elif node_type is Str:
            return self.evaluate(self.flow.names.get(node.s))
        elif node_type is Constant:
            return self.evaluate(self.flow.names.get(node.value))
        elif node_type is Attribute:
            value = self.evaluate(node.value)
            if value:
                if isinstance(value, SourceModule) and value.name in _TYPING_MODULES:
                    return MarkerObject(node.attr)
                return self.evaluate(value.get_attr(self, node.attr))
        else:
            # if isinstance(node, AST):
            #     log.warning('Unknown node type %r %r:\n%s', node_type, node, dump(node))
            # else:
            log.warning('Unknown node type %r %r', node_type, node)

        return None

    def make_composite(self, values: list[AST]) -> CompositeValue | None:
        rvalues = []
        for it in values:
            o = self.evaluate(it)
            if o is None:
                continue
            if type(o) is CompositeValue:
                rvalues.extend(o.values)
            else:
                rvalues.append(o)

        if rvalues:
            return CompositeValue(rvalues)

        return None
