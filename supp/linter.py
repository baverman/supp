from .util import Source, get_name_usages, dump_flows
from .astwalk import Extractor, SourceScope, ClassScope

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
            snames[name.name].used = True
            # print('!!!', name, snames[name.name])
        except KeyError:
            flow = scope.flow_at(name.location)
            result.append(('E02', 'Undefined name: {}'.format(name.name),
                           name.location[0], name.location[1], flow))

    for flow, name in scope.all_names:
        if name.name.startswith('_'): continue
        if not isinstance(flow.scope, IGNORED_SCOPES) and not hasattr(name, 'used'):
            # print('###', name)
            result.append(('W01', 'Unused name: {}'.format(name.name),
                name.location[0], name.location[1], flow))

    return result
