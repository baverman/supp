import builtins
import sys

VER = sys.version_info[:2]


range = builtins.range
string_types = (str,)
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


def reraise(tp, value, tb=None):
    if value.__traceback__ is not tb:
        raise value.with_traceback(tb)
    raise value


HAS_VAR_TYPE_HINTS = VER >= (3, 6)
HAS_WALRUS = VER >= (3, 8)
HAS_CONSTANTS = VER >= (3, 8)
