from .compat import iteritems


class MergedDict(object):
    def __init__(self, *dicts):
        self._dicts = dd = []
        for d in dicts:
            if type(d) == MergedDict:
                dd.extend(d._dicts)
            else:
                dd.append(d)

    def __getitem__(self, key):
        for p in self._dicts:
            try:
                return p[key]
            except KeyError:
                pass

        raise KeyError(key)

    def __contains__(self, key):
        return any(key in p for p in self._dicts)

    def iteritems(self):
        result = {}
        for p in reversed(self._dicts):
            result.update(p)

        return iteritems(result)

    items = iteritems

    def __iter__(self):
        return (r[0] for r in self.iteritems())

    def itervalues(self):
        return (r[1] for r in self.iteritems())

    values = itervalues

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
