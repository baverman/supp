from __future__ import print_function

import sys
from bisect import insort
from ast import iter_fields, Store, Load, NodeVisitor, parse, Tuple, List, AST

from .compat import iteritems, string_types

NESTED_INDEXED_NODES = Tuple, List


def clone_node(obj, **kwargs):
    new = AST.__new__(type(obj))
    new.__dict__.update(obj.__dict__, **kwargs)
    return new


class cached_property(object):
    cached = True

    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value

    @staticmethod
    def invalidate(obj, name):
        if name in obj.__class__.__dict__:
            try:
                delattr(obj, name)
            except AttributeError:
                pass


def insert_loc(locations, loc):
    if locations and locations[-1] < loc:
        locations.append(loc)
    else:
        insort(locations, loc)


class Location(object):
    def __init__(self, location):
        self.location = location

    def __lt__(self, other):
        return self.location < other.location

    def __repr__(self):
        return repr(self.location)


def dumptree(node, result, level):
    LW = '   '
    fields = [(k, v)
              for k, v in iter_fields(node)
              if (hasattr(v, '_fields') and not isinstance(v, Store)) or
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
            result.append('{} {}:'.format(LW * (level + 1), k))
            for child in v:
                dumptree(child, result, level + 2)
        else:
            result.append('{} {}:'.format(LW * (level + 1), k))
            dumptree(v, result, level + 2)

    return result


def dump(node):
    return '\n'.join(dumptree(node, [], 0))


def print_dump(node):
    print(dump(node))


def visitor(cls):
    v = type(cls.__name__, (cls, NodeVisitor), {})
    func = lambda node: v().process(node)
    func.visitor = v
    return func


class StopVisiting(Exception):
    def __init__(self, value):
        self.value = value


@visitor
class get_expr_end(object):
    def process(self, node):
        self.last_loc = node.lineno, node.col_offset + 1
        self.visit(node)
        return self.last_loc

    def visit_Store(self, node):
        pass

    def visit_Load(self, node):
        pass

    def __getattr__(self, name):
        def inner(node):
            try:
                self.last_loc = node.lineno, node.col_offset + 1
            except AttributeError:
                pass
            self.generic_visit(node)

        setattr(self, name, inner)
        return inner


@visitor
class get_name_usages(object):
    def process(self, node):
        self.locations = []
        self.visit(node)
        return self.locations

    def visit_Name(self, node):
        if isinstance(node.ctx, Load):
            self.locations.append((node.id, np(node)))


@visitor
class get_all_usages(object):
    def process(self, node):
        self.locations = []
        self.visit(node)
        return self.locations

    def visit_Name(self, node):
        if type(node.ctx) is Load:
            self.locations.append(('name', node.id, np(node), node))

    def visit_Attribute(self, node):
        if type(node.ctx) is Load:
            self.locations.append(('attr', node.attr, np(node), node))
        self.visit(node.value)


@visitor
class get_marked_atribute(object):
    def process(self, node):
        try:
            self.visit(node)
        except StopVisiting as e:
            return e.value

        return None

    def visit_Attribute(self, node):
        if marked(node.attr):
            raise StopVisiting(clone_node(node, attr=unmark(node.attr)))

        self.visit(node.value)


@visitor
class get_marked_name(object):
    def process(self, node):
        try:
            self.visit(node)
        except StopVisiting as e:
            return e.value

    def visit_Name(self, node):
        if isinstance(node.ctx, Load) and marked(node.id):
            raise StopVisiting(clone_node(node, id=unmark(node.id)))


def _join_level_pkg(level, package):
    return '.' * level + (package and package or '')


def join_pkg(package, module):
    if package.endswith('.'):
        return package + module
    else:
        return package + '.' + module


def split_pkg(package):
    if not package.strip('.'):
        return package, ''

    head, sep, tail = package.rpartition('.')
    if not head:
        if sep:
            head = sep
    elif head.endswith('.'):
        head += '.'
    return head, tail


@visitor
class get_marked_import(object):
    def process(self, node):
        try:
            self.visit(node)
        except StopVisiting as e:
            return e.value

    def visit_Import(self, node):
        for a in node.names:
            if marked(a.name):
                raise StopVisiting((unmark(a.name), None))

    def visit_ImportFrom(self, node):
        if node.module and marked(node.module):
            name = _join_level_pkg(node.level, unmark(node.module))
            raise StopVisiting((name, None))
        for a in node.names:
            if marked(a.name):
                name = _join_level_pkg(node.level, node.module)
                raise StopVisiting((name, unmark(a.name)))


def get_indexes_for_target(target, result, idx):
    if isinstance(target, NESTED_INDEXED_NODES):
        for i, r in enumerate(target.elts):
            nidx = idx[:]
            nidx.append(i)
            get_indexes_for_target(r, result, nidx)
    else:
        result.append((target, idx[:]))
        if idx:
            idx[-1] += 1

    return result


def np(node):
    return node.lineno, node.col_offset


SOURCE_MARK = '__supp_mark__'


def unmark(name):
    pos = name.find(SOURCE_MARK)
    result = name[:pos] + name[pos+len(SOURCE_MARK):]
    dpos = result.find('.', pos)
    if dpos >= 0:
        result = result[:dpos]
    return result


def marked(name):
    return SOURCE_MARK in name


class Source(object):
    def __init__(self, source, filename=None, position=None):
        self.filename = filename or '<string>'
        if position:
            ln, col = position
            lines = source.splitlines() or ['']
            line = lines[ln-1]
            lines[ln-1] = line[:col] + SOURCE_MARK + line[col:]
            self.source = '\n'.join(lines)
            self.lines = lines
        else:
            self.source = source

    @cached_property
    def tree(self):
        return parse(self.source, self.filename)

    @cached_property
    def lines(self):
        return self.source.splitlines() or ['']


def dump_flows(scope, fd=None):
    from .astwalk import LoopFlow

    fd = fd or sys.stdout
    if isinstance(fd, string_types):
        fd = open(fd, 'w')

    print('digraph G {', file=fd)
    print('rankdir=BT;', file=fd)
    print('node [shape=box];', file=fd)

    scopes = {}

    for level, flows in sorted(iteritems(scope.flows)):
        for flow in flows:
            try:
                l = scope.lines[flow.location[0]-1].strip() + r'\n'
            except IndexError:
                l = ''
            print(r'{} [label="{}\n{}{}"];'.format(
                id(flow),
                flow,
                l,
                flow._names), file=fd)
            scopes.setdefault(flow.scope, []).append((level, flow))

    def print_flows(flows):
        for _, flow in flows:
            for p in flow.parents:
                if isinstance(p, LoopFlow):
                    print('{} [label="loop"];'.format(id(p)), file=fd)
                    print('{} -> {};'.format(id(p), id(p.parent)), file=fd)
                print('{} -> {};'.format(id(flow), id(p)), file=fd)

    print_flows(scopes[scope])
    for s, flows in iteritems(scopes):
        if s is scope:
            continue
        print('subgraph {} {{'.format(id(s)), file=fd)
        print_flows(flows)
        print('}', file=fd)

    print('}', file=fd)
    fd.flush()
