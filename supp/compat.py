import sys

PY2 = sys.version_info[0] == 2

if PY2:
    import __builtin__ as builtins
    range = builtins.xrange
    reduce = builtins.reduce
    string_types = (str, unicode)

    iterkeys = lambda d: d.iterkeys()
    itervalues = lambda d: d.itervalues()
    iteritems = lambda d: d.iteritems()
    listkeys = lambda d: d.keys()
    listvalues = lambda d: d.values()
    listitems = lambda d: d.items()

    def nstr(data):
        if type(data) is unicode:
            return data.encode('utf-8')
        return data

    def hasattr(obj, name):
        try:
            getattr(obj, name)
            return True
        except AttributeError:
            return False
else:
    import builtins
    from functools import reduce
    range = builtins.range
    string_types = (str, )
    hasattr = builtins.hasattr

    iterkeys = lambda d: d.keys()
    itervalues = lambda d: d.values()
    iteritems = lambda d: d.items()
    listkeys = lambda d: list(d.keys())
    listvalues = lambda d: list(d.values())
    listitems = lambda d: list(d.items())

    def nstr(data):
        if type(data) is bytes:
            return data.decode()
        return data
