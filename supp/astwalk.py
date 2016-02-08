from __future__ import print_function
import string
from bisect import bisect
from collections import defaultdict
from contextlib import contextmanager
from ast import NodeVisitor, Attribute, Tuple, List, Subscript

from .util import Location, np, get_expr_end, insert_loc, cached_property, Name
from .compat import PY2, itervalues, builtins, iteritems
from . import compat

NESTED_INDEXED_NODES = Tuple, List
UNSUPPORTED_ASSIGMENTS = Attribute, Subscript
IMPORT_DELIMETERS = string.whitespace + '(,'
IMPORT_END_DELIMETERS = string.whitespace + '),.;'


def get_indexes_for_target(target, result, idx):
    if isinstance(target, NESTED_INDEXED_NODES):
        idx.append(0)
        for r in target.elts:
            get_indexes_for_target(r, result, idx)
        idx.pop()
    else:
        result.append((target, idx[:]))
        if idx:
            idx[-1] += 1

    return result


class ArgumentName(Name):
    def __init__(self, name, location, declared_at, func):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func

    def __repr__(self):
        return 'ArgumentName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class AssignedName(Name):
    def __init__(self, name, location, declared_at, value_node):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node

    def __repr__(self):
        return 'AssignedName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class ImportedName(Name):
    def __init__(self, name, location, declared_at, module,
                 mname=None, filename=None):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname
        self.filename = filename

    def resolve(self, project):
        try:
            return self._ref
        except AttributeError:
            pass

        if self.mname:
            if self.module.strip('.'):
                module = self.module + '.' + self.mname
            else:
                module = self.module + self.mname

            try:
                value = project.get_nmodule(module, self.filename)
            except ImportError:
                value = None

        if value is None:
            value = project.get_nmodule(self.module, self.filename)
            if self.mname:
                value = value.names[self.mname]

        if isinstance(value, ImportedName):
            value = value.resolve(project)

        self._ref = value
        return value

    def __repr__(self):
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname)


class UndefinedName(str):
    def __repr__(self):
        return 'UndefinedName({})'.format(self)


class MultiName(object):
    def __init__(self, names):
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.names)
            else:
                allnames.append(n)
        self.names = list(set(allnames))

    def __repr__(self):
        return 'MultiName({})'.format(self.names)


class Fork(object):
    def __init__(self, extractor):
        self.extractor = extractor
        self.parent = extractor.flow
        self.forks = []
        self.first_flow = None

    def do(self, *blocks):
        e = self.extractor
        p = self.parent
        flow = None
        for nodes in blocks:
            if nodes:
                e.flow = e.add_flow(np(nodes[0]), [p])
                flow = flow or e.flow
                if not self.first_flow:
                    self.first_flow = e.flow
                for n in nodes:
                    e.visit(n)
                p = e.flow

        self.forks.append(e.flow)
        return flow

    def empty(self):
        self.forks.append(self.parent)


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
                nrow = set(p.names.get(n, UndefinedName(n)) for p in parents)
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
        # cached_property.invalidate(self, 'names')
        # cached_property.invalidate(self, 'parent_names')
        return self

    def linkto(self, flow):
        self.parents.append(flow)
        # cached_property.invalidate(self, 'names')
        # cached_property.invalidate(self, 'parent_names')
        return self

    def __repr__(self):
        return '<Flow({location}, {level})>'.format(**vars(self))


class LoopFlow(object):
    def __init__(self, parent):
        self.parent = parent
        self._resolving = False
        self.virtual = True

    @property
    def names(self):
        if self._resolving:
            return {}

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


class Extractor(NodeVisitor):
    def __init__(self, source):
        self.filename = source.filename
        self.tree = source.tree
        self.top = SourceScope(source.lines, source.filename)
        self.scope = self.top
        self.flow = self.add_flow((1, 0))

    def process(self):
        for node in self.tree.body:
            self.visit(node)

        return self.top

    @contextmanager
    def fork(self, node):
        f = Fork(self)
        yield f
        self.join(node, f.parent, f.forks)

    def add_flow(self, loc, parents=None, level=None):
        return self.top.add_flow(Flow(self.scope, loc, parents), level=level)

    def add_region(self, node, flow=None, end_node=None):
        # print node, end_node, np(node), get_expr_end(end_node or node)
        self.top.add_region(flow or self.flow,
                            np(node),
                            get_expr_end(end_node or node))

    def join(self, node, parent, forks):
        last_line = get_expr_end(node)[0]
        loc = last_line + 1, -parent.level
        self.flow = self.add_flow(loc, forks, parent.level)

    def shift(self, node, nodes):
        flow = self.flow
        self.flow = self.add_flow(np(nodes[0]), [flow])
        for n in nodes:
            self.visit(n)
        self.join(node, flow, [self.flow])

    def visit_Assign(self, node):
        eend = get_expr_end(node.value)
        for targets in node.targets:
            for name, _ in get_indexes_for_target(targets, [], []):
                if isinstance(name, UNSUPPORTED_ASSIGMENTS):
                    continue
                self.flow.add_name(AssignedName(name.id, eend, np(name), node.value))
        self.visit(node.value)

    def visit_If(self, node):
        self.visit(node.test)
        with self.fork(node) as fork:
            fork.do(node.body)
            if node.orelse:
                fork.do(node.orelse)
            else:
                fork.empty()

    def visit_For(self, node):
        with self.fork(node) as fork:
            fork.empty()
            fork.do(node.body)
            for nn, _idx in get_indexes_for_target(node.target, [], []):
                fork.first_flow.add_name(
                    AssignedName(nn.id, np(node.body[0]), np(nn), node.iter))

            self.visit(node.iter)
            fork.first_flow.linkto(LoopFlow(self.flow))

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_While(self, node):
        self.visit(node.test)
        with self.fork(node) as fork:
            fork.empty()
            fork.do(node.body)
            fork.first_flow.linkto(LoopFlow(self.flow))

        if node.orelse:
            self.shift(node, node.orelse)

    def visit_Import(self, node):
        loc = get_expr_end(node)
        start = np(node)
        for a in node.names:
            name = a.asname or a.name.partition('.')[0]
            declared_at = self.top.find_id_loc(name, start)
            self.flow.add_name(ImportedName(name, loc, declared_at, a.name,
                                            None, self.filename))

    def visit_ImportFrom(self, node):
        loc = get_expr_end(node)
        start = np(node)
        for a in node.names:
            name = a.asname or a.name
            declared_at = self.top.find_id_loc(name, start)
            module = '.' * node.level + (node.module or '')
            self.flow.add_name(ImportedName(name, loc, declared_at, module,
                                            a.name, self.filename))

    def visit_TryExcept(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                flow = fork.do(h.body)
                if h.name:
                    nn = h.name
                    flow.add_name(AssignedName(nn.id, np(h.body[0]), np(nn), h.type))

    def visit_Try(self, node):
        with self.fork(node) as fork:
            fork.do(node.body, node.orelse)
            for h in node.handlers:
                flow = fork.do(h.body)
                if h.name:
                    flow.add_name(AssignedName(h.name, np(h.body[0]), np(h), h.type))

    @contextmanager
    def nest(self):
        scope = self.scope
        flow = self.flow
        yield scope, flow
        self.scope = scope
        self.flow = flow

    def visit_FunctionDef(self, node):
        for d in node.decorator_list:
            self.visit(d)
        with self.nest() as (_, flow):
            self.scope = FuncScope(self.scope, node)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body:
                self.visit(n)
            self.scope.last_flow = self.flow

    def visit_Lambda(self, node):
        with self.nest():
            self.scope = FuncScope(self.scope, node, True)
            self.flow = self.top.add_flow(self.scope.flow, level=-1)
            self.add_region(node.body)
            self.visit(node.body)

    def visit_ClassDef(self, node):
        with self.nest() as (_, flow):
            self.scope = ClassScope(self.scope, node)
            flow.add_name(self.scope)
            self.flow = self.top.add_flow(self.scope.flow, True)
            if self.flow.level < 0:
                self.add_region(node.body[0])
            for n in node.body:
                self.visit(n)

    def visit_expr(self, node):
        self.add_region(node)
        self.generic_visit(node)

    visit_Expr = visit_expr
    visit_Dict = visit_expr
    visit_Set = visit_expr
    visit_List = visit_expr
    visit_Tuple = visit_expr

    def visit_ListComp(self, node):
        flow = self.flow
        for g in node.generators:
            self.add_region(g.iter)
            self.visit(g.iter)
            self.flow = self.add_flow(np(g.target), [self.flow], -1)
            for nn, _idx in get_indexes_for_target(g.target, [], []):
                self.flow.add_name(AssignedName(nn.id, np(node), np(nn), g.iter))
            if g.ifs:
                self.add_region(g.ifs[0], end_node=g.ifs[-1])
                for inode in g.ifs:
                    self.visit(inode)

        elt = getattr(node, 'elt', None) or node.value
        self.add_region(node, end_node=elt)
        self.visit(elt)
        self.flow = flow

    visit_GeneratorExp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_SetComp = visit_ListComp

    def visit_With(self, node):
        if PY2:
            items = [node]
        else:
            items = node.items

        for it in items:
            if it.optional_vars:
                for nn, _idx in get_indexes_for_target(it.optional_vars, [], []):
                    self.flow.add_name(AssignedName(nn.id, np(node.body[0]), np(nn), node))

        self.generic_visit(node)

    def visit_Global(self, node):
        self.scope.globals.update(node.names)
