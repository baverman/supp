from .util import cached_property, Source
from .astwalk import Extractor


class ModuleCache(object):
    def __init__(self, project):
        self.project = project
        self._cache = {}

    def get(self, name, filename):
        try:
            return self._cache[filename]
        except KeyError:
            pass

        module = self._cache[filename] = SourceModule(name, self.project, filename)
        return module

    def changed(self, filename):
        try:
            module = self._cache[filename]
        except KeyError:
            pass
        else:
            module.invalidate()


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

    def invalidate(self):
        try:
            del self.scope
        except AttributeError:
            pass
