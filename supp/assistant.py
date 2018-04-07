from __future__ import print_function
import re
import logging

from .util import (Source, print_dump, get_marked_atribute, split_pkg,
                   get_marked_name, get_marked_import, get_all_usages, join_pkg)
from .evaluator import EvalCtx
from .nast import extract_scope

log = logging.getLogger('supp.assistant')


def list_packages(project, root, filename):
    root = project.norm_package(root, filename)
    return sorted(r for r in project.list_packages(root))


def assist(project, source, position, filename=None, debug=False):
    source = Source(source, filename, position)
    ctx = EvalCtx(project)
    ln, col = position
    line = source.lines[ln - 1][:col]
    if line.lstrip().startswith('from ') and ' import ' not in line:
        iname = line.rpartition(' ')[2]
        package, sep, prefix = iname.rpartition('.')
        if (not package or package.startswith('.')) and sep:
            package += '.'
        return prefix, list_packages(project, package, filename)

    debug and print_dump(source.tree)

    marked_import = get_marked_import(source.tree)
    if marked_import:
        head, tail = marked_import
        if tail is None:
            head, tail = split_pkg(head)
            return tail, list_packages(project, head, filename)
        else:
            plist = list_packages(project, head, filename)
            module = project.get_nmodule(head, filename)
            return tail, sorted(set(plist) | set(module.attr_list(ctx)))

    scope = extract_scope(source, project)

    prefix = re.split(r'(\.|\s|\()', line)[-1]
    attr = get_marked_atribute(source.tree)
    names = {}
    if attr:
        value = ctx.evaluate(attr.value)
        if value:
            names = value.attr_list(ctx)
    else:
        name = get_marked_name(source.tree)
        if name:
            names = name.flow.names_at(position)

    return prefix, sorted(names)


def _loc(location, filename):
    return {'loc': location, 'file': filename}


def location(project, source, position, filename=None, debug=False):
    source = Source(source, filename, position)

    debug and print_dump(source.tree)
    scope = extract_scope(source, project)

    result = []
    marked_import = get_marked_import(source.tree)
    ctx = EvalCtx(project)

    if marked_import:
        head, tail = marked_import
        if tail is None:
            name = project.get_nmodule(head, filename)
        else:
            if not tail:
                full = head
                head, tail = split_pkg(head)
            else:
                full = join_pkg(head, tail)

            module = project.get_nmodule(head, filename)
            name = module.get_attr(ctx, tail)
            if not name:
                name = project.get_nmodule(full, filename)

        result = ctx.declarations(name, [])
    else:
        node = get_marked_name(source.tree) or get_marked_atribute(source.tree)
        if node:
            result = ctx.declarations(node, [])

    locs = []
    for r in result:
        if isinstance(r, list):
            locs.append([_loc(n.declared_at, n.filename) for n in r])
        else:
            locs.append(_loc(r.declared_at, r.filename))

    return locs


def usages(project, source, filename=None):
    source = Source(source, filename)
    scope = extract_scope(source, project)
    ctx = EvalCtx(project)

    for utype, nname, loc, node in get_all_usages(source.tree):
        # print(scope, node)
        value = ctx.declarations(node, [])

        if value:
            if utype == 'attr':
                print('GUT', utype, nname, loc, value)
        else:
            print('BAD', utype, nname, loc, vars(node))
