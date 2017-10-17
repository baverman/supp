import logging

from .util import Source, get_name_usages, np
from .name import MultiName, ArgumentName, ImportedName
from .scope import SourceScope, ClassScope
from .nast import extract_scope
from .compat import itervalues
from .evaluator import EvalCtx


IGNORED_SCOPES = SourceScope, ClassScope
log = logging.getLogger('supp.linter')


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
    scope = extract_scope(source, project)
    name_usages = get_name_usages(source.tree)

    # from .util import print_dump
    # print_dump(scope.source.tree)

    for name in name_usages:
        location = np(name)
        try:
            flow = name.flow
        except AttributeError:
            result.append(('E42', 'UNKNOWN NAME: {}'.format(name.id),
                           location[0], location[1], None))
            continue

        snames = flow.names_at(location)
        try:
            sname = snames[name.id]
            # print('!!!', name.id, sname)
        except KeyError:
            result.append(('E02', 'Undefined name: {}'.format(name.id),
                           location[0], location[1], flow))
        else:
            if sname.name == 'locals' and sname.location == (0, 0):
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


def check_names(project, source, filename=None):
    source = Source(source, filename)
    scope = extract_scope(source, project)
    ctx = EvalCtx(project)

    name_usages = get_name_usages(source.tree)
    for name in name_usages:
        print('@@@', name.id, np(name))
        value = ctx.evaluate(name)
        if value:
            print('GUT', name.id, np(name), value)
        else:
            print('BAD', name.id, np(name))


if __name__ == '__main__':
    import os
    import sys
    from .project import Project
    check_names(Project([os.getcwd()]), open(sys.argv[1]).read(), sys.argv[1])
