from ast import Name

from .util import np
from .astwalk import ImportedName


def evaluate(project, scope, node):
    if isinstance(node, Name):
        names = scope.names_at(np(node))
        name = names.get(node.id)
        if name:
            if isinstance(name, ImportedName):
                return name.resolve(project)
