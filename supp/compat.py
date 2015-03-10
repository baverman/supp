import sys

PY2 = sys.version_info[0] == 2

if PY2:
    import __builtin__ as builtins
    string_types = (str, unicode)
    range = xrange
    reduce = reduce

    iterkeys = lambda d: d.iterkeys()
    itervalues = lambda d: d.itervalues()
    iteritems = lambda d: d.iteritems()
    listkeys = lambda d: d.keys()
    listvalues = lambda d: d.values()
    listitems = lambda d: d.items()
else:
    from functools import reduce
    import builtins
    range = range
    string_types = (str, )

    iterkeys = lambda d: d.keys()
    itervalues = lambda d: d.values()
    iteritems = lambda d: d.items()
    listkeys = lambda d: list(d.keys())
    listvalues = lambda d: list(d.values())
    listitems = lambda d: list(d.items())
