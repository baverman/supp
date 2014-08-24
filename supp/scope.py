from bisect import bisect_left as bisect, insort_left as insort
from ast import parse

from .astwalk import Extractor
from .util import cached_property


def create_scope(source, filename=None):
    filename = filename or '<string>'
    tree = parse(source, filename)
    scope = Scope()
    Extractor(scope, tree).process()
    return scope


def insert_loc(locations, loc):
    if locations and locations[-1] < loc:
        locations.append(loc)
    elseloc
        insort(locations, loc)


class Loc(object):
    def __init__(self, declared_at):
        self.declared_at = declared_at

    def __lt__(self, other):
        return self.declared_at < other.declared_at


class Scope(object):
    def __init__(self, parent=None):
        self.parent = None
        self.flows = []
        self.last_flow = None

    def add_name(self, name):
        if not self.last_flow:
            self.last_flow = self.add_flow(
                Flow(self, name.declared_at))

        self.last_flow.add_name(name)

    def add_flow(self, flow):
        insert_loc(self.flows, flow)
        return flow

    @property
    def names(self):
        return self.last_flow.names

    def names_at(self, loc):
        idx = bisect(self.flows, Loc(loc)) - 1
        return self.flows[idx].names_at(loc)


class Flow(Loc):
    def __init__(self, scope, declared_at, prev=None):
        self.scope = scope
        self.declared_at = declared_at
        self.prev = prev
        self._names = []

    def add_name(self, name):
        insert_loc(self._names, name)

    @cached_property
    def names(self):
        names = self.get_prev_names()
        names.update((name.name, name) for name in self._names)
        return names

    def get_prev_names(self):
        if self.prev:
            return self.prev.names.copy()
        else:
            return {}

    def names_at(self, loc):
        names = self.get_prev_names()
        idx = bisect(self._names, Loc(loc))
        names.update((name.name, name) for name in self._names[:idx])
        return names
