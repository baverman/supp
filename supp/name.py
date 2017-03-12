import logging

from .util import Location, cached_property
from .compat import iteritems


class Name(Location):
    def __init__(self, name, location=None):
        self.name = name
        self.location = location

    def __repr__(self):
        return '{}({}, {})'.format(self.__class__.__name__,
                                   self.name, self.location)

    @property
    def filename(self):
        return self.scope and self.scope.top.filename


class ArgumentName(Name):
    def __init__(self, idx, name, location, declared_at, func):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.func = func
        self.idx = idx

    def __repr__(self):
        return 'ArgumentName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)

    def resolve(self):
        return self.func.get_argument(self)


class AssignedName(Name):
    def __init__(self, name, location, declared_at, value_node):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.value_node = value_node

    def __repr__(self):
        return 'AssignedName({}, {}, {})'.format(
            self.name, self.location, self.declared_at)


class AdditionalNameWrapper(object):
    def __init__(self, value, names):
        self.value = value
        self._names = names

    @property
    def scope(self):
        return self.value.scope

    @property
    def declared_at(self):
        return self.value.declared_at

    @property
    def attrs(self):
        names = self._names.copy()
        if self.value:
            names.update(self.value.attrs)
        return names


class FailedImport(str):
    names = {}


class ImportedName(Name):
    def __init__(self, name, location, declared_at, module,
                 mname=None, is_star=False):
        Name.__init__(self, name, location)
        self.declared_at = declared_at
        self.module = module
        self.mname = mname
        self.is_star = is_star

    def resolve(self):
        try:
            return self._ref
        except AttributeError:
            pass

        value = None
        if self.mname:
            if self.module.strip('.'):
                module = self.module + '.' + self.mname
            else:
                module = self.module + self.mname

            try:
                value = self.scope.top.project.get_nmodule(module, self.filename)
            except ImportError:
                pass

        if value is None:
            try:
                value = self.scope.top.project.get_nmodule(self.module, self.filename)
            except ImportError:
                logging.getLogger('supp.import').error(
                    'Failed import of %s from %s', self.module, self.filename)
                value = FailedImport(self.module)
            else:
                if self.mname:
                    value = value.attrs.get(self.mname)

        if not self.mname and value:
            prefix = self.module + '.'
            names = {}
            for mname in self.scope.top._imports:
                if mname.startswith(prefix):
                    name = mname[len(prefix):].partition('.')[0]
                    names[name] = iname = ImportedName(name, (0, 0), (0, 0),
                                                       prefix + name, None)
                    iname.scope = self.scope
            if names:
                value = AdditionalNameWrapper(value, names)

        self._ref = value
        return value

    def __repr__(self):
        return 'ImportedName({}, {}, {}, {}, {})'.format(
            self.name, self.location, self.declared_at, self.module, self.mname)


class RuntimeName(Name):
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.location = (0, 0)

    @cached_property
    def attrs(self):
        try:
            return {k: RuntimeName(k, v) for k, v in iteritems(vars(self.value))}
        except TypeError:
            return {k: RuntimeName(k, getattr(self.value, k, None)) for k in dir(self.value)}


class UndefinedName(str):
    location = (0, 0)

    def __lt__(self, other):
        return True

    def __repr__(self):
        return 'UndefinedName({})'.format(self)


class MultiName(object):
    def __init__(self, names):
        allnames = []
        for n in names:
            if isinstance(n, MultiName):
                allnames.extend(n.alt_names)
            else:
                allnames.append(n)
        self.alt_names = list(set(allnames))
        n = self.alt_names[0]
        if type(n) == UndefinedName:
            self.name = str(n)
        else:
            self.name = n.name

    def __repr__(self):
        return 'MultiName({})'.format(self.alt_names)
