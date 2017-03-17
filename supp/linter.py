from .util import Source, get_name_usages
from .name import MultiName, ArgumentName, ImportedName
from .scope import SourceScope, ClassScope
from .astwalk import extract_scope
from .compat import itervalues

IGNORED_SCOPES = SourceScope, ClassScope


def use_name(name):
    if isinstance(name, MultiName):
        for n in name.alt_names:
            n.used = True
    else:
        name.used = True


def lint(project, source, filename=None):
    source = Source(source, filename)
    try:
        source.tree
    except SyntaxError as e:
        return [('E01', e.msg, e.lineno, e.offset, None)]

    result = []
    scope = extract_scope(project, source)
    name_usages = get_name_usages(source.tree)

    for name, location in name_usages:
        snames = scope.names_at(location)
        try:
            sname = snames[name]
            # print('!!!', name, sname)
        except KeyError:
            flow = scope.flow_at(location)
            result.append(('E02', 'Undefined name: {}'.format(name),
                           location[0], location[1], flow))
        else:
            if sname.name == 'locals' and sname.location == (0, 0):
                flow = scope.flow_at(location)
                for n in itervalues(flow.names_at(location)):
                    if getattr(n, 'scope', None) is flow.scope:
                        use_name(n)

            use_name(sname)

    for flow, name in scope.all_names:
        w = 'W01'
        message = 'Unused name: {}'
        if hasattr(name, 'used'):
            continue
        if name.name.startswith('_'):
            continue
        if getattr(name, 'is_star', None):
            continue
        if isinstance(flow.scope, IGNORED_SCOPES):
            if isinstance(name, ImportedName):
                w = 'W02'
                message = 'Unused import: {}'
                if name.module == '__future__':
                    continue
            else:
                continue
        if (isinstance(name, ArgumentName) and
                isinstance(flow.scope.parent, ClassScope)):
            continue

        # print('###', name)
        result.append((w, message.format(name.name),
                       name.declared_at[0], name.declared_at[1], flow))

    return result
