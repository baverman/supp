from __future__ import print_function
import string
from bisect import bisect
from collections import defaultdict

from .util import Location, np, insert_loc, cached_property, get_indexes_for_target
from .compat import PY2, itervalues, builtins, iteritems
from .name import ArgumentName, MultiName, UndefinedName, Name
from . import compat

IMPORT_DELIMETERS = string.whitespace + '(,'
IMPORT_END_DELIMETERS = string.whitespace + '),.;'


class Scope(object):
    def __init__(self, parent):
        self.parent = parent
        self.locals = set()
        self.globals = set()


class FileScope(object):
    @cached_property
    def filename(self):
        s = self.parent
        while s:
            try:
                return getattr(s, 'filename')
            except AttributeError:
                s = s.parent

        return None


class FuncScope(Scope, Location, FileScope):
    def __init__(self, parent, node, is_lambda=False):
        Scope.__init__(self, parent)
        self.args = []
        self.declared_at = np(node)
        if is_lambda:
            self.name = 'lambda'
            self.location = np(node.body)
        else:
            self.name = node.name
            self.location = np(node.body[0])

        for n in node.args.args:
            if PY2:
                for nn, _idx in get_indexes_for_target(n, [], []):
                    self.args.append(ArgumentName(nn.id, self.location, np(nn), self))
            else:
                self.args.append(ArgumentName(n.arg, self.location, np(n), self))

        for n in (node.args.vararg, node.args.kwarg):
            if n:
                if PY2:
                    self.args.append(ArgumentName(n, self.location, self.location, self))
                else:
                    self.args.append(ArgumentName(n.arg, self.location, np(n), self))

        self.flow = Flow(self, self.location)
        for arg in self.args:
            self.flow.add_name(arg)

    @property
    def names(self):
        return self.last_flow.names

    def __repr__(self):
        return 'FuncScope({}, {})'.format(self.name, self.location)


class ClassScope(Scope, Location, FileScope):
    def __init__(self, parent, node):
        Scope.__init__(self, parent)
        self.name = node.name
        self.declared_at = np(node)
        self.location = np(node.body[0])
        self.flow = Flow(self, self.location)

    @property
    def names(self):
        return self.parent.names


class Region(Location):
    def __init__(self, flow, start, end):
        self.flow = flow
        self.location = start
        self.end = end

    def __repr__(self):
        return 'Region({0.flow}, {0.location}, {0.end})'.format(self)


class BuiltinScope(object):
    @cached_property
    def names(self):
        names = {k: Name(k, (0, 0)) for k in dir(builtins)}
        names.update({k: Name(k, (0, 0))
                      for k in dir(compat)
                      if k.startswith('__')})
        return names


class SourceScope(Scope):
    def __init__(self, lines, filename=None):
        Scope.__init__(self, BuiltinScope())
        self.filename = filename
        self.lines = lines
        self.flows = defaultdict(list)
        self.allflows = []
        self.scope_flows = defaultdict(list)
        self.regions = []
        self._global_names = {}

    def get_level(self, loc, check_colon=False):
        l, c = loc
        try:
            line = self.lines[l - 1][:c]
        except IndexError:
            return c

        if len(line) < c:
            return c

        if check_colon:
            rsline = line.rstrip()
            if rsline.endswith(':'):
                return -1

        sline = line.lstrip()
        return len(line) - len(sline)

    def add_flow(self, flow, check_colon=False, level=None):
        if level is None:
            level = self.get_level(flow.location, check_colon)
        flow.level = level
        flow.top = self
        insert_loc(self.flows[level], flow)
        if level != -1:
            insert_loc(self.allflows, flow)
            insert_loc(self.scope_flows[flow.scope], flow)
        return flow

    def add_region(self, flow, start, end):
        region = Region(flow, start, end)
        insert_loc(self.regions, region)

    def add_global(self, name):
        self._global_names[name.name] = name

    @cached_property
    def names(self):
        names = self.flows[0][-1].names.copy()
        names.update(self._global_names)
        return names

    @property
    def exported_names(self):
        return {k: v
                for k, v in iteritems(self.names)
                if getattr(v, 'location', None) != (0, 0)}

    def flow_at(self, loc):
        lloc = Location(loc)

        idx = bisect(self.regions, lloc) - 1
        while idx >= 0:
            region = self.regions[idx]
            if region.end > loc:
                return region.flow

            idx -= 1

        flows = self.allflows
        level = self.get_level(loc)
        while True:
            idx = bisect(flows, lloc) - 1
            flow = flows[idx]
            slevel = self.scope_flows[flow.scope][0].level
            if level < slevel or slevel == -1:
                flows = self.scope_flows[flow.scope.parent]
            else:
                break

        # print('!!!', lloc, flow, flow.parents, flows[max(0, idx-3):idx+1])
        flow_level = abs(flow.level - level)
        if flow_level == 0:
            return flow

        if flow.location[0] < loc[0] and flow.level <= level:
            return flow

        result = []
        cf = flow
        floc = flow.location
        while idx >= 0 and cf.location[0] == floc[0]:
            if (abs(cf.level - level) == 0):
                result.append(cf)
            for f in cf.parents:
                if f.virtual:
                    continue
                if (abs(f.level - level) == 0):
                    result.append(f)

            idx -= 1
            cf = flows[idx]

        return result and max(result) or flow

    def names_at(self, loc):
        flow = self.flow_at(loc)
        # print self.regions, flow, loc, self.get_level(loc), flow._names
        return flow.names_at(loc)

    @property
    def all_names(self):
        for flows in itervalues(self.flows):
            for flow in flows:
                for name in flow._names:
                    yield flow, name

    def find_id_loc(self, id, start):
        sl, pos = start
        source = '\n'.join(self.lines[sl-1:sl+50])
        source_len = len(source)
        while True:
            pos = source.find(id, pos + 1)
            if pos < 0:
                break

            if pos == 0 or source[pos-1] in IMPORT_DELIMETERS:
                ep = pos + len(id)
                if ep >= source_len or source[ep] in IMPORT_END_DELIMETERS:
                    return sl + source.count('\n', 0, pos), pos - source.rfind('\n', 0, pos) - 1

        return start


def resolved_parent_names(parents):
    for p in parents:
        names = p.names
        if not isinstance(names, UnresolvedNames):
            yield names


class Flow(Location):
    def __init__(self, scope, location, parents=None, virtual=False):
        self.scope = scope
        self.location = location
        self.parents = parents or []
        self.level = None
        self._names = []
        self.virtual = virtual

    def add_name(self, name):
        name.scope = self.scope
        if name.name in self.scope.globals:
            self.top.add_global(name)
        else:
            self.scope.locals.add(name.name)
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
                nrow = set(r.get(n, UndefinedName(n))
                           for r in resolved_parent_names(parents))
                if len(nrow) == 1:
                    names[n] = list(nrow)[0]
                else:
                    names[n] = MultiName(list(nrow))

            return names
        else:
            if self.scope.parent:
                pnames = self.scope.parent.names
                outer_names = set(pnames).difference(self.scope.locals)
                return {n: pnames[n] for n in outer_names}
            else:
                return {}

    def names_at(self, loc):
        names = self.parent_names.copy()
        # print(loc, self, names)
        idx = bisect(self._names, Location(loc))
        names.update((name.name, name) for name in self._names[:idx])
        return names

    def loop(self):
        self.parents.append(LoopFlow(self))
        return self

    def linkto(self, flow):
        self.parents.append(flow)
        return self

    def __repr__(self):
        return '<Flow({location}, {level})>'.format(**vars(self))


class UnresolvedNames(dict):
    pass


class LoopFlow(object):
    def __init__(self, parent):
        self.parent = parent
        self._resolving = False
        self.virtual = True

    @property
    def names(self):
        if self._resolving:
            return UnresolvedNames()

        try:
            return self._names
        except AttributeError:
            pass

        self._resolving = True
        try:
            result = self._names = self.parent.names
        finally:
            self._resolving = False

        return result