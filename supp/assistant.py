from .compat import itervalues
from .util import Source, SOURCE_PH
from .astwalk import Extractor, ImportedName


def assist(project, source, position, filename=None):
    source = Source(source, filename, position)
    ln, col = position
    line = source.lines[ln - 1][:col]
    if line.lstrip().startswith('from ') and not ' import ' in line:
        iname = line.rpartition(' ')[2]
        package, sep, prefix = iname.rpartition('.')
        if (not package or package.startswith('.')) and sep:
            package += '.'
        return sorted(r for r in project.list_packages(package, filename) if r.startswith(prefix))
    else:
        scope = Extractor(source).process()
        names = scope.names_at(position)
        for name in itervalues(names):
            if isinstance(name, ImportedName):
                if name.module.endswith(SOURCE_PH):
                    iname = name.module[:-len(SOURCE_PH)]
                    package, _, prefix = iname.rpartition('.')
                    return sorted(r for r in project.list_packages(package, filename) if r.startswith(prefix))
                elif name.mname and name.mname.endswith(SOURCE_PH):
                    package = name.module
                    prefix = name.mname[:-len(SOURCE_PH)]
                    return sorted(r for r in project.list_packages(package, filename) if r.startswith(prefix))

