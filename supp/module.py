from .util import cached_property, Source
from .astwalk import Extractor


class SourceModule(object):
    def __init__(self, name, project, filename):
        self.project = project
        self.name = name
        self.filename = filename

    @cached_property
    def scope(self):
        e = Extractor(Source(open(self.filename).read(), self.filename))
        return e.process()

    @property
    def names(self):
        return self.scope.names
