from __future__ import print_function
import re

from .util import (Source, print_dump, get_marked_atribute, np, split_pkg,
                   get_marked_name, get_marked_import, get_all_usages, join_pkg)
from .evaluator import evaluate, declarations
from .astwalk import Extractor


def list_packages(project, root, filename):
    root = project.norm_package(root, filename)
    return sorted(r for r in project.list_packages(root))


def assist(project, source, position, filename=None, debug=False):
    source = Source(source, filename, position)
    ln, col = position
    line = source.lines[ln - 1][:col]
    if line.lstrip().startswith('from ') and ' import ' not in line:
        iname = line.rpartition(' ')[2]
        package, sep, prefix = iname.rpartition('.')
        if (not package or package.startswith('.')) and sep:
            package += '.'
        return prefix, list_packages(project, package, filename)

    e = Extractor(source)
    debug and print_dump(e.tree)

    marked_import = get_marked_import(e.tree)
    if marked_import:
        head, tail = marked_import
        if tail is None:
            head, tail = split_pkg(head)
            return tail, list_packages(project, head, filename)
        else:
            plist = list_packages(project, head, filename)
            module = project.get_nmodule(head, filename)
            return tail, sorted(set(plist) | set(module.names))

    scope = e.process()
    scope.resolve_star_imports(project)

    prefix = re.split(r'(\.|\s)', line)[-1]
    attr = get_marked_atribute(e.tree)
    if attr:
        value = evaluate(project, scope, attr.value)
        if value:
            names = value.names
        else:
            names = {}
    else:
        names = scope.names_at(position)

    return prefix, sorted(names)


def _loc(location, filename):
    return {'loc': location, 'file': filename}


def location(project, source, position, filename=None, debug=False):
    source = Source(source, filename, position)

    e = Extractor(source)
    debug and print_dump(e.tree)
    scope = e.process()
    scope.resolve_star_imports(project)

    result = []
    marked_import = get_marked_import(e.tree)
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
            name = module.names.get(tail)
            if not name:
                name = project.get_nmodule(full, filename)

        result = declarations(project, None, name, [])
    else:
        node = get_marked_name(e.tree) or get_marked_atribute(e.tree)
        if node:
            result = declarations(project, scope, node, [])

    locs = []
    for r in result:
        if isinstance(r, list):
            locs.append([_loc(n.declared_at, n.filename) for n in r])
        else:
            locs.append(_loc(r.declared_at, r.filename))

    return locs


def usages(project, source, filename=None):
    source = Source(source, filename)
    e = Extractor(source)
    scope = e.process()
    scope.resolve_star_imports(project)

    for utype, nname, loc, node in get_all_usages(source.tree):
        # print(scope, node)
        value = declarations(project, scope, node, [])

        if value:
            if utype == 'attr':
                print('GUT', utype, nname, loc, value)
        else:
            print('BAD', utype, nname, loc, vars(node))
