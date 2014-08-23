from bisect import bisect, insort
from ast import parse

from .astwalk import Extractor
from .util import cached_property


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
        loc = flow.declared_at
        flows = self.flows
        if flows and loc > flows[-1][0]:
            flows.append((loc, flow))
        else:
            insort(flows, (loc, flow))

        return flow

    @property
    def names(self):
        return self.last_flow.names

    def names_at(self, loc):
        idx = bisect(self.flows, (loc, None)) - 1
        return self.flows[idx][1].names_at(loc)


class Flow(object):
    def __init__(self, scope, declared_at, prev=None):
        self.scope = scope
        self.declared_at = declared_at
        self.prev = prev
        self._names = []

    def add_name(self, name):
        loc = name.declared_at
        names = self._names
        if names and loc > names[-1][0]:
            names.append((loc, name))
        else:
            insort(names, (loc, name))

    @cached_property
    def names(self):
        if self.prev:
            names = self.prev.names.copy()
        else:
            names = {}

        names.update((name.name, name) for _, name in self._names)
        return names

    def names_at(self, loc):
        if self.prev:
            names = self.prev.names.copy()
        else:
            names = {}

        idx = bisect(self._names, (loc, None))
        names.update((name.name, name) for _, name in self._names[:idx])
        return names
