from __future__ import print_function

import sys
from bisect import insort
from ast import iter_fields, Store, Load, NodeVisitor, parse, Tuple, List, AST

try:
    from ast import Starred
except ImportError:
    class Starred: pass  # type: ignore[no-redef]

from .compat import iteritems, string_types

if False:
    import typing as t, abc
    from .scope import Scope, Flow, SourceScope
    from ast import ImportFrom, Import, Name as AstName, Attribute, Subscript
    from functools import cached_property as cached_property

    T = t.TypeVar('T')
    R = t.TypeVar('R', covariant=True)
    P = t.ParamSpec('P')
    loc_t = tuple[int, int]

    Targets = AstName | Attribute | Subscript

    class Comparable(t.Protocol):
        def __lt__(self, other: t.Any) -> bool:
            ...

    CompT = t.TypeVar('CompT', bound=Comparable)

    class VisitProtocol(t.Protocol[P, R]):
        def process(self, *args: P.args, **kwargs: P.kwargs) -> R:
            ...


NESTED_INDEXED_NODES = Tuple, List


def clone_node(obj, **kwargs):
    # type: (AST, t.Any) -> AST
    new = AST.__new__(type(obj))
    new.__dict__.update(obj.__dict__, **kwargs)
    new._orig = obj  # type: ignore[attr-defined]
    return new


class cached_property(object):  # type: ignore[no-redef]
    cached = True

    def __init__(self, func):  # type: ignore[no-untyped-def]
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):  # type: ignore[no-untyped-def]
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


def context_property(func):
    # type: (t.Callable[..., R]) -> t.Callable[..., R]
    def inner(self, ctx, *args, **kwargs):
        # type: (T, t.Any, t.Any, t.Any) -> R
        try:
            cv = self._ctx_values  # type: ignore[attr-defined]
        except AttributeError:
            cv = self._ctx_values = {}  # type: ignore[attr-defined]
        else:
            try:
                return cv[func.__name__]  # type: ignore[no-any-return]
            except KeyError:
                pass

        val = cv[func.__name__] = func(self, ctx, *args, **kwargs)
        return val
    return inner


class AttributeException(Exception): pass


class Location(object):
    def __init__(self, location):
        # type: (loc_t) -> None
        self.location = location

    def __lt__(self, other):
        # type: (t.Self) -> bool
        return self.location < other.location

    def __repr__(self):
        # type: () -> str
        return repr(self.location)


def insert_loc(locations, loc):
    # type: (list[CompT], CompT) -> None
    if locations and locations[-1] < loc:
        locations.append(loc)
    else:
        insort(locations, loc)


def dumptree(node, result, level):
    # type: (AST, list[str], int) -> list[str]
    LW = '   '
    fields = [(k, v)
              for k, v in iter_fields(node)
              if (hasattr(v, '_fields') and not isinstance(v, Store) and not isinstance(v, Load)) or
                 (isinstance(v, list) and v and hasattr(v[0], '_fields'))]
    field_names = set(k for k, _ in fields)

    result.append('{} {} {}'.format(
        LW * level,
        type(node).__name__,
        ', '.join('{}: {}'.format(k, v)
                  for k, v in sorted(iteritems(vars(node)))
                  if k not in field_names)))

    for k, v in fields:
        if isinstance(v, list):
            result.append('{} {}[]: '.format(LW * (level + 1), k))
            for child in v:
                dumptree(child, result, level + 2)
        else:
            result.append('{} {}:'.format(LW * (level + 1), k))
            dumptree(v, result, level + 2)

    return result


def dump(node):
    # type: (AST) -> str
    return '\n'.join(dumptree(node, [], 0))


def print_dump(node):
    # type: (AST) -> None
    print(dump(node))


def visitor(cls):
    # type: (type[VisitProtocol[P, R]]) -> t.Callable[P, R]
    def func(*args, **kwargs):
        # type: (P.args, P.kwargs) -> R
        return cls().process(*args, **kwargs)
    func.visitor = cls  # type: ignore[attr-defined]
    return func


class StopVisiting(Exception):
    def __init__(self, value):
        # type: (t.Any) -> None
        self.value = value


class get_expr_end_visitor(NodeVisitor):
    def process(self, node):
        # type: (AST) -> loc_t
        self.last_loc = node.lineno, node.col_offset + 1
        self.visit(node)
        return self.last_loc

    def visit_Store(self, node):
        # type: (AST) -> None
        pass

    def visit_Load(self, node):
        # type: (AST) -> None
        pass

    def __getattr__(self, name):
        # type: (str) -> t.Callable[[AST], None]
        def inner(node):
            # type: (AST) -> None
            try:
                self.last_loc = node.lineno, node.col_offset + 1
            except AttributeError:
                pass
            self.generic_visit(node)

        setattr(self, name, inner)
        return inner


class get_name_usages_visitor(NodeVisitor):
    def process(self, node):
        # type: (AST) -> list[AstName]
        self.locations = []  # type: list[AstName]
        self.visit(node)
        return self.locations

    def visit_Name(self, node):
        # type: (AstName) -> None
        if isinstance(node.ctx, Load):
            self.locations.append(node)


class get_all_usages_visitor(NodeVisitor):
    def process(self, node):
        # type: (AST) -> list[tuple[str, str, loc_t, AST]]
        self.locations = []  # type: list[tuple[str, str, loc_t, AST]]
        self.visit(node)
        return self.locations

    def visit_Name(self, node):
        # type: (AstName) -> None
        if type(node.ctx) is Load:
            self.locations.append(('name', node.id, np(node), node))

    def visit_Attribute(self, node):
        # type: (Attribute) -> None
        if type(node.ctx) is Load:
            self.locations.append(('attr', node.attr, np(node), node))
        self.visit(node.value)


class StopNodeVisitor(NodeVisitor):
    def process(self, node):
        # type: (AST) -> t.Any
        try:
            self.visit(node)
        except StopVisiting as e:
            return e.value

        return None


class get_marked_atribute_visitor(StopNodeVisitor):
    def visit_Attribute(self, node):
        # type: (Attribute) -> None
        if marked(node.attr):
            raise StopVisiting(clone_node(node, attr=unmark(node.attr)))

        self.visit(node.value)


class get_marked_name_visitor(StopNodeVisitor):
    def visit_Name(self, node):
        # type: (AstName) -> None
        if type(node.ctx) == Load and marked(node.id):
            raise StopVisiting(clone_node(node, id=unmark(node.id)))


class get_any_marked_name_visitor(StopNodeVisitor):
    def visit_Name(self, node):
        # type: (AstName) -> None
        if marked(node.id):
            raise StopVisiting(clone_node(node, id=unmark(node.id)))


def _join_level_pkg(level, package):
    # type: (int, str | None) -> str
    return '.' * level + (package and package or '')


def join_pkg(package, module):
    # type: (str, str) -> str
    if package.endswith('.'):
        return package + module
    else:
        return package + '.' + module


def split_pkg(package):
    # type: (str) -> tuple[str, str]
    if not package.strip('.'):
        return package, ''

    head, sep, tail = package.rpartition('.')
    if not head:
        if sep:
            head = sep
    elif head.endswith('.'):
        head += '.'
    return head, tail


class get_marked_import_visitor(StopNodeVisitor):
    def visit_Import(self, node):
        # type: (Import) -> None
        for a in node.names:
            if marked(a.name):
                raise StopVisiting((unmark(a.name), None))

    def visit_ImportFrom(self, node):
        # type: (ImportFrom) -> None
        if node.module and marked(node.module):
            name = _join_level_pkg(node.level, unmark(node.module))
            raise StopVisiting((name, None))
        for a in node.names:
            if marked(a.name):
                name = _join_level_pkg(node.level, node.module)
                raise StopVisiting((name, unmark(a.name)))


def get_indexes_for_target(target, result, idx):
    # type: (AST, list[tuple[Targets, list[int]]], list[int]) -> list[tuple[Targets, list[int]]]
    if isinstance(target, NESTED_INDEXED_NODES):
        for i, r in enumerate(target.elts):
            nidx = idx[:]
            nidx.append(i)
            get_indexes_for_target(r, result, nidx)
    else:
        if type(target) is Starred:
            target = target.value
        result.append((target, idx[:]))  # type: ignore[arg-type]
        if idx:
            idx[-1] += 1

    return result


def np(node):
    # type: (AST) -> loc_t
    return node.lineno, node.col_offset


SOURCE_MARK = '__supp_mark__'


def unmark(name):
    # type: (str) -> str
    pos = name.find(SOURCE_MARK)
    result = name[:pos] + name[pos+len(SOURCE_MARK):]
    dpos = result.find('.', pos)
    if dpos >= 0:
        result = result[:dpos]
    return result


def marked(name):
    # type: (str) -> bool
    return SOURCE_MARK in name


class Source(object):
    def __init__(self, source, filename=None, position=None):
        # type: (str, str | None, tuple[int, int] | None) -> None
        self.orig_source = source
        self.filename = filename or '<string>'
        if position:
            ln, col = position
            lines = source.splitlines() or ['']
            if ln > len(lines):
                lines.append('')
            line = lines[ln-1]
            lines[ln-1] = line[:col] + SOURCE_MARK + line[col:]
            self.source = '\n'.join(lines)
            self.lines = lines
        else:
            self.source = source

    def with_mark(self, position):
        # type: (tuple[int, int]) -> Source
        return Source(self.orig_source, self.filename, position)

    @cached_property
    def tree(self):
        # type: () -> AST
        return parse(self.source, self.filename)

    @cached_property
    def lines(self):
        # type: () -> list[str]
        return self.source.splitlines() or ['']


def dump_flows(scope, fd=None):
    # type: (SourceScope, t.Optional[t.IO[str]]) -> None
    from functools import partial
    from .scope import LoopFlow

    fd = fd or sys.stdout
    if isinstance(fd, string_types):
        fd = open(fd, 'w')

    pp = partial(print, file=fd)

    pp('digraph G {')
    pp('rankdir=BT;')
    pp('node [shape=box];')

    scopes = {}  # type: dict[Scope, list[Flow]]

    for flow in scope._all_flows:
        pp(r'{} [label="{}{}"];'.format(
            id(flow),
            flow.hint,
            flow._names))
        scopes.setdefault(flow.scope, []).append(flow)

    def print_flows(scope, flows):
        # type: (Scope, list[Flow]) -> None
        for flow in flows:
            if flow.parents:
                for p in flow.parents:
                    if isinstance(p, LoopFlow):
                        pp('{} [label="loop"];'.format(id(p)))
                        pp('{} -> {};'.format(id(p), id(p.parent)))
                    pp('{} -> {};'.format(id(flow), id(p)))
            elif scope.parent:
                pp('{} -> {};'.format(id(flow), id(scope.parent.flow)))

    print_flows(scope, scopes[scope])
    for s, flows in iteritems(scopes):
        if s is scope:
            continue
        pp('subgraph {} {{'.format(id(s)))
        print_flows(s, flows)
        pp('}')

    pp('}')
    fd.flush()


get_expr_end = visitor(get_expr_end_visitor)
get_any_marked_name = visitor(get_any_marked_name_visitor)
get_name_usages = visitor(get_name_usages_visitor)
get_marked_import = visitor(get_marked_import_visitor)
get_marked_atribute = visitor(get_marked_atribute_visitor)
get_marked_name = visitor(get_marked_name_visitor)
get_all_usages = visitor(get_all_usages_visitor)
