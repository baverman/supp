import re

from .compat import itervalues
from .util import (Source, unmark, marked, print_dump,
                   get_marked_atribute, get_marked_name)
from .evaluator import evaluate
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
    else:
        e = Extractor(source)
        debug and print_dump(e.tree)
        scope = e.process()
        names = scope.names_at(position)
        for name in itervalues(names):
            if isinstance(name, ImportedName):
                if marked(name.module):
                    package, _, prefix = unmark(name.module).rpartition('.')
                    return prefix, list_packages(project, package, filename)
                elif name.mname and marked(name.mname):
                    package = name.module
                    prefix = unmark(name.mname)
                    plist = list_packages(project, package, filename)
                    module = project.get_module(project.norm_package(package, filename))
                    return prefix, sorted(set(plist) | set(module.names))

        prefix = re.split(r'(\.|\s)', line)[-1]
        _, expr = get_marked_atribute(e.tree)
        if expr:
            value = evaluate(project, scope, expr)
            if value:
                names = value.names
            else:
                names = {}

        return prefix, sorted(names)


def location(project, source, position, filename=None, debug=False):
    source = Source(source, filename, position)

    e = Extractor(source)
    debug and print_dump(e.tree)
    scope = e.process()

    mname = get_marked_name(e.tree)
    if mname:
        names = scope.names_at(position)
        name = names.get(mname)
        if name:
            if isinstance(name, ImportedName):
                name = name.resolve(project)
                return name.declared_at, name.filename
            return name.declared_at, None
    else:
        mname, expr = get_marked_atribute(e.tree)
        value = evaluate(project, scope, expr)
        name = value.names.get(mname)
        if isinstance(name, ImportedName):
            name = name.resolve(project)
        return name.declared_at, name.filename

    return None, None
