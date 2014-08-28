from ast import parse
from bisect import insort, bisect
from collections import defaultdict

from .astwalk import Extractor, MultiName, UndefinedName
from .util import cached_property, Location


def create_scope(source, filename=None):
    filename = filename or '<string>'
    return ModuleScope(source, filename)


def insert_loc(locations, loc):
    if locations and locations[-1] < loc:
        locations.append(loc)
    else:
        insort(locations, loc)


class ModuleScope(object):
    def __init__(self, source, filename):
        self.parent = None
        self.lines = source.splitlines() or ['']
        self.flows = defaultdict(list)

        flow = self.add_flow((1, 0))
        tree = parse(source, filename)
        Extractor(self, flow, tree).process()

    def get_level(self, loc):
        l, c = loc
        line = self.lines[l - 1][:c]
        sline = line.lstrip()
        return len(line) - len(sline)

    def get_level_flows(self, level):
        try:
            return self.flows[level]
        except KeyError:
            pass

        levels = sorted(self.flows)
        return self.flows[levels[bisect(levels, level) - 1]]

    def add_flow(self, location, parents=None):
        flow = Flow(self, location, parents)
        insert_loc(self.flows[self.get_level(location)], flow)
        return flow

    @property
    def names(self):
        return self.flows[0][-1].names

    def names_at(self, loc):
        flows = self.get_level_flows(self.get_level(loc))
        idx = bisect(flows, Location(loc)) - 1
        return flows[idx].names_at(loc)


class Flow(Location):
    def __init__(self, scope, location, parents=None):
        self.scope = scope
        self.location = location
        self.parents = parents or []
        self._names = []

    def add_name(self, name):
        insert_loc(self._names, name)

    @cached_property
    def names(self):
        names = self.parent_names.copy()
        names.update((name.name, name) for name in self._names)
        return names

    @cached_property
    def parent_names(self):
        parents = self.parents[:]
        if len(parents) == 1:
            return parents[0].names
        elif len(parents) > 1:
            names = {}

            nameset = set()
            for p in parents:
                nameset.update(p.names)

            for n in nameset:
                nrow = set(p.names.get(n, UndefinedName(n)) for p in parents)
                if len(nrow) == 1:
                    names[n] = list(nrow)[0]
                else:
                    names[n] = MultiName(list(nrow))

            return names
        else:
            return {}

    def names_at(self, loc):
        names = self.parent_names.copy()
        idx = bisect(self._names, Location(loc))
        names.update((name.name, name) for name in self._names[:idx])
        return names

    def __repr__(self):
        return '<Flow({})>'.format(self.location)

    def loop(self):
        self.parents.append(LoopFlow(self))


class LoopFlow(object):
    def __init__(self, parent):
        self._names = parent._names

    @cached_property
    def names(self):
        return {n.name: n for n in self._names}

