from .util import Source, get_name_usages, dump_flows
from .astwalk import Extractor, SourceScope, ClassScope, MultiName, ArgumentName

IGNORED_SCOPES = SourceScope, ClassScope


def lint(project, source, filename=None):
    source = Source(source, filename)
    try:
        source.tree
    except SyntaxError as e:
        return [('E01', 'Invalid syntax', e.lineno, e.offset)]

    result = []
    scope = Extractor(source).process()
    # dump_flows(scope, open('/tmp/boo.dot', 'w'))
    name_usages = get_name_usages(source.tree)

    for name in name_usages:
        snames = scope.names_at(name.location)
        try:
            sname = snames[name.name]
            # print('!!!', name, sname)
        except KeyError:
            flow = scope.flow_at(name.location)
            result.append(('E02', 'Undefined name: {}'.format(name.name),
                           name.location[0], name.location[1], flow))
        else:
            if isinstance(sname, MultiName):
                for n in sname.names:
                    n.used = True
            else:
                sname.used = True

    for flow, name in scope.all_names:
        if hasattr(name, 'used'): continue

        if name.name.startswith('_'): continue

        if isinstance(flow.scope, IGNORED_SCOPES): continue

        if (isinstance(name, ArgumentName) and
            isinstance(flow.scope.parent, ClassScope)): continue

        # print('###', name)
        result.append(('W01', 'Unused name: {}'.format(name.name),
            name.location[0], name.location[1], flow))

    return result
