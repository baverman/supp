import re

from .compat import itervalues
from .util import Source, unmark, marked
from .astwalk import Extractor, ImportedName


def list_packages(project, root, filename, prefix):
    root = project.norm_package(root, filename)
    return sorted(r for r in project.list_packages(root) if r.startswith(prefix))


def assist(project, source, position, filename=None):
    source = Source(source, filename, position)
    ln, col = position
    line = source.lines[ln - 1][:col]
    if line.lstrip().startswith('from ') and not ' import ' in line:
        iname = line.rpartition(' ')[2]
        package, sep, prefix = iname.rpartition('.')
        if (not package or package.startswith('.')) and sep:
            package += '.'
        return prefix, list_packages(project, package, filename, prefix)
    else:
        scope = Extractor(source).process()
        names = scope.names_at(position)
        for name in itervalues(names):
            if isinstance(name, ImportedName):
                if marked(name.module):
                    package, _, prefix = unmark(name.module).rpartition('.')
                    return prefix, list_packages(project, package, filename, prefix)
                elif name.mname and marked(name.mname):
                    package = name.module
                    prefix = unmark(name.mname)
                    plist = list_packages(project, package, filename, prefix)
                    module = project.get_module(project.norm_package(package, filename))
                    return prefix, sorted(set(plist) | set(module.names))

        prefix = re.split(r'\.\s', line)[-1]
        return prefix, sorted(r for r in names if r.startswith(prefix))
