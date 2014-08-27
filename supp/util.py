class cached_property(object):
    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self

        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


class Loc(object):
    def __init__(self, declared_at):
        self.declared_at = declared_at

    def __lt__(self, other):
        return self.declared_at < other.declared_at

