from __future__ import print_function

from bisect import insort
from ast import iter_fields, Store, NodeVisitor, parse

from .compat import iteritems


class cached_property(object):
    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


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


LW = '   '
def dumptree(node, result, level):
    fields = [(k, v) for k, v in iter_fields(node)
        if (hasattr(v, '_fields') and not isinstance(v, Store))
            or (isinstance(v, list) and v and hasattr(v[0], '_fields'))]
    field_names = set(k for k, v in fields)

    result.append('{} {} {}'.format(LW * level, type(node).__name__,
        ', '.join('{}: {}'.format(k, v) for k, v in sorted(iteritems(vars(node)))
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


class GetExprEnd(NodeVisitor):
    def __call__(self, node):
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


def np(node):
    return node.lineno, node.col_offset


SOURCE_PH = '__supp_ph__'

class Source(object):
    def __init__(self, source, filename=None, position=None):
        self.filename = filename or '<string>'
        if position:
            ln, col = position
            lines = source.splitlines() or ['']
            line = lines[ln-1]
            lines[ln-1] = line[:col] + SOURCE_PH + line[col:]
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
