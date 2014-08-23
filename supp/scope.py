from bisect import bisect_left as bisect, insort_left as insort
from ast import parse

from .astwalk import Extractor
from .util import cached_property


class Loc(object):
    def __init__(self, declared_at):
        self.declared_at = declared_at

    def __lt__(self, other):
        return self.declared_at < other.declared_at


def create_scope(source, filename=None):
    filename = filename or '<string>'
    tree = parse(source, filename)
    scope = Scope()
    Extractor(scope, tree).process()
    return scope


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
        flows = self.flows
        if flows and flows[-1] < flow:
            flows.append(flow)
        else:
            insort(flows, flow)

        return flow

    @property
    def names(self):
        return self.last_flow.names

    def names_at(self, loc):
        idx = bisect(self.flows, Loc(loc)) - 1
        return self.flows[idx].names_at(loc)


class Flow(object):
    def __init__(self, scope, declared_at, prev=None):
        self.scope = scope
        self.declared_at = declared_at
        self.prev = prev
        self._names = []

    def __lt__(self, other):
        return self.declared_at < other.declared_at

    def add_name(self, name):
        names = self._names
        if names and names[-1] < name:
            names.append(name)
        else:
            insort(names, name)

    @cached_property
    def names(self):
        if self.prev:
            names = self.prev.names.copy()
        else:
            names = {}

        names.update((name.name, name) for name in self._names)
        return names

    def names_at(self, loc):
        if self.prev:
            names = self.prev.names.copy()
        else:
            names = {}

        idx = bisect(self._names, Loc(loc))
        names.update((name.name, name) for name in self._names[:idx])
        return names
