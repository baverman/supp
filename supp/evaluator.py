from ast import Name

from .util import np
from .astwalk import ImportedName


def evaluate(project, scope, node):
    if isinstance(node, Name):
        names = scope.names_at(np(node))
        name = names.get(node.id)
        if name:
            return evaluate(project, scope, name)
    elif isinstance(node, ImportedName):
        return evaluate(project, node.scope, node.resolve(project))
    elif getattr(node, 'names', None):
        return node
