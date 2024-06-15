import os

from textwrap import dedent
from ast import Lambda, With, Call, Subscript, Dict

from supp.compat import iteritems, PY2
from supp.name import (AssignedName, UndefinedName, MultiName,
                       ImportedName, ArgumentName)
from supp.scope import SourceScope, FuncScope, ClassScope
from supp.util import Source, print_dump, dump_flows
from supp.nast import extract, marked_flow


if PY2:
    class AsyncWith: pass
else:
    from ast import AsyncWith


def sp(source):
    source = dedent(source)
    cursors = []
    parts = source.split(type(source)('|'))
    pos = 0
    source = ''
    for p in parts[:-1]:
        pos += len(p)
        source += p
        line = source.count('\n') + 1
        column = pos - source.rfind('\n') - 1
        cursors.append((line, column))

    return type(source)('').join(parts), cursors


def csp(source, filename=None, debug=False, flow_graph=False):
    source, p = sp(source)
    return create_scope(source, filename, debug, flow_graph), p


def create_scope(source, filename=None, debug=False, flow_graph=False):
    source = Source(source, filename)
    (debug or os.environ.get('DEBUG')) and print_dump(source.tree)
    scope = SourceScope(source)
    scope.parent = None
    extract(source.tree, scope.flow)
    flow_graph or os.environ.get('FLOW_GRAPH') and dump_flows(scope, '/tmp/scope-dump.dot')
    return scope


def names_at(scope, p, project=None, debug=False):
    scope = scope.with_mark(p, debug)
    scope.parent = None
    debug and print_dump(scope.source.tree)
    extract(scope.source.tree, scope.flow)
    flow = marked_flow(scope)
    if project:
        scope.resolve_star_imports(project)
    import os
    if os.environ.get('PDB'):
        import ipdb; ipdb.set_trace()
    return flow.names_at(p)


def get_value(name):
    if isinstance(name, AssignedName):
        if isinstance(name.value_node, Lambda):
            return 'lambda'
        if isinstance(name.value_node, (With, AsyncWith)):
            return 'with'
        if isinstance(name.value_node, Call):
            return 'func()'
        if isinstance(name.value_node, Subscript):
            return 'item[]'
        if isinstance(name.value_node, Dict):
            return '{}'
        if name.value_node is None:
            return 'none'
        if hasattr(name.value_node, 'elts'):
            return 'listitem'
        if hasattr(name.value_node, 'id'):
            return name.value_node.id
        if PY2:
            return name.value_node.n
        else:
            return name.value_node.value
    elif isinstance(name, UndefinedName):
        return 'undefined'
    elif isinstance(name, MultiName):
        return set(get_value(r) for r in name.alt_names)
    elif isinstance(name, ImportedName):
        if name.mname:
            return 'import:{0.module}:{0.mname}'.format(name)
        else:
            return 'import:{0.module}'.format(name)
    elif isinstance(name, ArgumentName):
        return '{}.arg'.format(name.func.name, name.name)
    elif isinstance(name, FuncScope):
        return 'func'
    elif isinstance(name, ClassScope):
        return 'class'
    else:
        raise Exception('Unknown name type', name, type(name))


def nvalues(names):
    return {k: get_value(v) for k, v in iteritems(names)}
