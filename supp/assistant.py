from __future__ import print_function
import re

from .util import (Source, print_dump, get_marked_atribute, np,
                   get_marked_name, get_marked_import, get_all_usages)
from .evaluator import evaluate, declarations
from .astwalk import Extractor, ImportedName


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
        is_module, iname = marked_import
        package, _, prefix = iname.rpartition('.')
        if is_module:
            return prefix, list_packages(project, package, filename)
        else:
            plist = list_packages(project, package, filename)
            module = project.get_nmodule(package, filename)
            return prefix, sorted(set(plist) | set(module.names))

    scope = e.process()
    scope.resolve_star_imports(project)

    prefix = re.split(r'(\.|\s)', line)[-1]
    _, expr = get_marked_atribute(e.tree)
    if expr:
        value = evaluate(project, scope, expr)
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

    marked_import = get_marked_import(e.tree)
    if marked_import:
        is_module, iname = marked_import
        package, _, prefix = iname.rpartition('.')
        if is_module:
            module = project.get_nmodule(iname, filename)
            return [_loc((1, 0), module.filename)]
        else:
            module = project.get_nmodule(package, filename)
            name = module.names.get(prefix)
            if isinstance(name, ImportedName):
                name = name.resolve(project)
            return [_loc(name.declared_at, name.filename)]

    mname = get_marked_name(e.tree)
    if mname:
        names = scope.names_at(position)
        name = names.get(mname)
        if name:
            result = declarations(project, scope, name, [])
    else:
        mname, expr = get_marked_atribute(e.tree)
        value = evaluate(project, scope, expr)
        name = value.names.get(mname)
        result = declarations(project, value.scope.top, name, [])

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
        value = None
        if utype == 'name':
            names = scope.names_at(np(node))
            value = names.get(node.id)

        # value = evaluate(project, scope, node)
        if value:
            print(nname, loc, value)
        else:
            print('!!', utype, nname, loc, node)
