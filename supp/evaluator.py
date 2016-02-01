from ast import Name
from .util import np


class ImportObject(object):
    def __init__(self, project, filename, name):
        self.project = project
        self.name = name
        self.filename = filename

    @property
    def names(self):
        value = self.project.get_nmodule(self.name.module, self.filename)
        if self.name.mname:
            value = value.names[self.name.mname]
        return value.names



def evaluate(project, scope, node, filename):
    if isinstance(node, Name):
        names = scope.names_at(np(node))
        try:
            return ImportObject(project, filename, names[node.id])
        except KeyError:
            pass
