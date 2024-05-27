from ast import Attribute, Subscript, Load, NodeVisitor

from .compat import PY2
from .scope import FuncScope, Flow, SourceScope, ClassScope
from .name import AssignedName, ImportedName
from .util import (np, get_expr_end, get_indexes_for_target, visitor, get_any_marked_name)

if PY2:
    UNSUPPORTED_ASSIGMENTS = Subscript
else:
    from ast import Starred
    UNSUPPORTED_ASSIGMENTS = Subscript, Starred


if False:
    import typing as t
    import ast
    from .scope import LoopFlow
    from .util import Source
    from .project import Project

    T = t.TypeVar('T')


def extract_scope(source, project):
    # type: (Source, Project) -> SourceScope
    scope = SourceScope(source)
    extract(source.tree, scope.flow)
    scope.resolve_star_imports(project)
    return scope


def marked_flow(scope):
    # type: (SourceScope) -> Flow | None
    name = get_any_marked_name(scope.source.tree)  # type: ast.Name
    if name and hasattr(name, 'flow'):
        marked_id = name._orig.id  # type: ignore[attr-defined]
        for n in name.flow._names:
            if n.name == marked_id:
                n.name = name.id
                if marked_id in name.flow.scope.locals:
                    name.flow.scope.locals.remove(marked_id)
                    name.flow.scope.locals.add(name.id)
        return name.flow  # type: ignore[no-any-return]
    return None


class extract_visitor(NodeVisitor):
    def process(self, tree, flow):
        # type: (ast.AST, Flow) -> Flow
        self.top = flow.scope.top
        self.flow = flow
        self.generic_visit(tree)
        return flow

    def make_flow(self, hint, parents):
        # type: (str, list[Flow]) -> Flow
        return self.top.add_flow(Flow(hint, self.flow.scope, parents))  # type: ignore[arg-type]

    def visit_in_flow(self, nodes, flow):
        # type: (list[t.Any] | t.Any, Flow) -> Flow
        cur = self.flow
        self.flow = flow
        if nodes:
            if type(nodes) == list:
                for n in nodes:
                    self.visit(n)
            else:
                self.visit(nodes)  # type: ignore[arg-type]
        result = self.flow
        self.flow = cur
        return result

    def visit_Assign(self, node):
        # type: (ast.Assign) -> None
        eend = get_expr_end(node.value)
        for targets in node.targets:
            for name, _ in get_indexes_for_target(targets, [], []):
                if isinstance(name, Attribute):
                    self.top.add_attr_assign(self.flow.scope, name, node.value)
                elif isinstance(name, UNSUPPORTED_ASSIGMENTS):
                    continue
                else:
                    name.flow = self.flow  # type: ignore[attr-defined]
                    self.flow.add_name(AssignedName(name.id, eend, np(name), node.value))

        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        # type: (ast.AnnAssign) -> None
        if node.value:
            eend = get_expr_end(node.value)
        else:
            eend = get_expr_end(node)
        name = node.target
        if isinstance(name, Attribute):
            self.top.add_attr_assign(self.flow.scope, name, node.value)  # type: ignore[arg-type]  # TODO
        elif isinstance(name, UNSUPPORTED_ASSIGMENTS):
            pass
        elif node.value:
            name.flow = self.flow  # type: ignore[attr-defined]
            self.flow.add_name(AssignedName(name.id, eend, np(name), node.value))
        self.generic_visit(node)

    def visit_If(self, node):
        # type: (ast.If) -> None
        self.visit(node.test)
        cur = self.flow
        body = self.visit_in_flow(node.body, self.make_flow('if', [cur]))
        orelse = self.visit_in_flow(node.orelse, self.make_flow('else', [cur]))
        self.flow = self.make_flow('join', [body, orelse])
        self.flow.scope.flow = self.flow

    def visit_For(self, node):
        # type: (ast.For | ast.AsyncFor) -> None
        self.visit(node.iter)
        cur = self.flow

        body_start = self.make_flow('for', [cur])
        for nn, _idx in get_indexes_for_target(node.target, [], []):
            name = nn  # type: ast.Name # type: ignore[assignment]
            body_start.add_name(AssignedName(name.id, np(node.body[0]), np(name), node.iter))
        body = self.visit_in_flow(node.body, body_start)
        body_start.loop(body)

        orelse = self.visit_in_flow(node.orelse, self.make_flow('for-else', [cur, body]))

        self.flow = self.make_flow('join', [orelse])
        self.flow.scope.flow = self.flow


    visit_AsyncFor = visit_For

    def visit_While(self, node):
        # type: (ast.While) -> None
        self.visit(node.test)
        cur = self.flow

        body_start = self.make_flow('while', [cur])
        body = self.visit_in_flow(node.body, body_start)
        body_start.loop(body)

        orelse = self.visit_in_flow(node.orelse,
                                    self.make_flow('while-else', [cur, body]))

        self.flow = self.make_flow('join', [orelse])
        self.flow.scope.flow = self.flow

    def visit_Import(self, node):
        # type: (ast.Import) -> None
        loc = get_expr_end(node)
        start = np(node)
        for a in node.names:
            qualified = False
            if a.asname:
                name = a.asname
                iname = a.name
            else:
                name, sep, _ = a.name.partition('.')
                qualified = bool(sep)
                iname = name
                self.top._imports.append(a.name)

            declared_at = self.top.find_id_loc(name, start)
            self.flow.add_name(ImportedName(name, loc, declared_at, iname, None,
                                            qualified=qualified))

    def visit_ImportFrom(self, node):
        # type: (ast.ImportFrom) -> None
        loc = get_expr_end(node)
        start = np(node)
        for a in node.names:
            name = a.asname or a.name
            declared_at = self.top.find_id_loc(name, start)
            module = '.' * node.level + (node.module or '')
            if name == '*':
                self.top._star_imports.append((loc, declared_at, module, self.flow))
            else:
                self.flow.add_name(ImportedName(name, loc, declared_at, module, a.name))

    def visit_TryExcept(self, node):
        # type: (ast.Try) -> None
        cur = self.flow
        body = self.visit_in_flow(node.body, self.make_flow('try', [cur]))
        handlers = []
        for h in node.handlers:
            fh = self.make_flow('except', [cur, body])
            if h.name:
                if PY2:
                    fh.add_name(AssignedName(h.name.id, np(h.body[0]), np(h), h.type))
                else:
                    fh.add_name(AssignedName(h.name, np(h.body[0]), np(h), h.type))  # type: ignore[arg-type]
            if h.type:
                self.visit(h.type)
            handlers.append(self.visit_in_flow(h.body, fh))

        orelse = self.visit_in_flow(node.orelse,
                                    self.make_flow('try-else', [body]))

        self.flow = self.make_flow('join', [orelse] + handlers)
        self.flow.scope.flow = self.flow
        if hasattr(node, 'finalbody'):
            self.visit_in_flow(node.finalbody, self.flow)

    visit_Try = visit_TryExcept

    def visit_FunctionDef(self, node):
        # type: (ast.FunctionDef) -> None
        for d in node.decorator_list:
            self.visit(d)

        for df in node.args.defaults:
            self.visit(df)

        if not PY2:
            for a in node.args.args:
                a.annotation and self.visit(a.annotation)
            for kw in node.args.kwonlyargs:
                kw.annotation and self.visit(kw.annotation)
            if node.args.vararg and node.args.vararg.annotation:
                self.visit(node.args.vararg.annotation)
            if node.args.kwarg and node.args.kwarg.annotation:
                self.visit(node.args.kwarg.annotation)
            node.returns and self.visit(node.returns)

        cur = self.flow
        scope = FuncScope(cur.scope, node, self.top)
        cur.add_name(scope)  # type: ignore[arg-type]  # TODO
        self.visit_in_flow(node.body, scope.flow)
        self.flow = cur

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node):
        # type: (ast.Lambda) -> None
        for d in node.args.defaults:
            self.visit(d)

        if not PY2:
            for a in node.args.args:
                a.annotation and self.visit(a.annotation)
            for kw in node.args.kwonlyargs:
                kw.annotation and self.visit(kw.annotation)

        cur = self.flow
        scope = FuncScope(cur.scope, node, self.top)
        self.visit_in_flow(node.body, scope.flow)

    def visit_ClassDef(self, node):
        # type: (ast.ClassDef) -> None
        cur = self.flow
        self.visit_in_flow(node.decorator_list, cur)
        self.visit_in_flow(node.bases, cur)
        scope = ClassScope(cur.scope, node, top=self.top)
        cur.add_name(scope)  # type: ignore[arg-type]  # TODO
        self.visit_in_flow(node.body, scope.flow)
        self.flow = cur

    def visit_Return(self, node):
        # type: (ast.Return) -> None
        self.flow.scope.returns.append(node.value)  # type: ignore[attr-defined]
        self.generic_visit(node)

    def visit_ListComp(self, node):
        # type: (ast.ListComp | ast.GeneratorExp | ast.DictComp | ast.SetComp) -> None
        p = cur = self.flow
        for g in node.generators:
            self.visit_in_flow(g.iter, p)
            pp = p
            p = self.make_flow('comp', [p])
            for nn, _idx in get_indexes_for_target(g.target, [], []):
                name = nn  # type: ast.Name # type: ignore[assignment]
                name.flow = pp  # type: ignore[attr-defined]
                p.add_name(AssignedName(name.id, np(node), np(name), g.iter))

            if g.ifs:
                for inode in g.ifs:
                    self.visit_in_flow(inode, p)

        elt = getattr(node, 'elt', None) or node.value  # type: ast.AST # type: ignore[union-attr]
        self.visit_in_flow(elt, p)

        if hasattr(node, 'key'):
            self.visit_in_flow(node.key, p)

        self.flow = self.make_flow('comp-join', [cur, p])
        self.flow.scope.flow = self.flow

    visit_GeneratorExp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_SetComp = visit_ListComp

    def visit_With(self, node):
        # type: (ast.With | ast.AsyncWith) -> None
        if PY2:
            items = [node]
        else:
            items = node.items

        for it in items:
            if it.optional_vars:
                for nn, _idx in get_indexes_for_target(it.optional_vars, [], []):
                    name = nn  # type: ast.Name # type: ignore[assignment]
                    self.flow.add_name(AssignedName(name.id, np(node.body[0]), np(name), node))

        self.generic_visit(node)

    visit_AsyncWith = visit_With

    def visit_Global(self, node):
        # type: (ast.Global) -> None
        self.flow.scope.globals.update(node.names)

    def visit_Name(self, node):
        # type: (ast.Name) -> None
        if type(node.ctx) is Load:
            node.flow = self.flow  # type: ignore[attr-defined]

    def visit_NamedExpr(self, node):
        # type: (ast.NamedExpr) -> None
        eend = get_expr_end(node.value)
        name = node.target
        name.flow = self.flow  # type: ignore[attr-defined]
        self.flow.add_name(AssignedName(name.id, eend, np(name), node.value))
        self.generic_visit(node)


extract = visitor(extract_visitor)
