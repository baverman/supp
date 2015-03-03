from .util import Source, get_name_usages
from .astwalk import Extractor, SourceScope


def lint(project, source, filename=None):
    source = Source(source, filename)
    try:
        source.tree
    except SyntaxError as e:
        return [('E01', 'Invalid syntax', e.lineno, e.offset)]

    result = []
    scope = Extractor(source).process()
    name_usages = get_name_usages(source.tree)
    for name in name_usages:
        snames = scope.names_at(name.location)
        try:
            snames[name.name].used = True
        except KeyError:
            result.append(('E02', 'Undefined name: {}'.format(name.name),
                name.location[0], name.location[1]))

    for flow, name in scope.all_names:
        if name.name.startswith('_'): continue
        if not isinstance(flow.scope, SourceScope) and not hasattr(name, 'used'):
            result.append(('W01', 'Unused name: {}'.format(name.name),
                name.location[0], name.location[1]))

    return result
