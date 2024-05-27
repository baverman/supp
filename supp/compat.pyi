import typing as t

T = t.TypeVar('T')
K = t.TypeVar('K')
V = t.TypeVar('V')

builtins: object

string_types = (str,)

PY2: bool

def iteritems(data: t.Mapping[K, V]) -> t.Iterable[tuple[K, V]]:
    ...

def itervalues(data: t.Mapping[K, V]) -> t.Iterable[V]:
    ...

def iterkeys(data: t.Mapping[K, V]) -> t.Iterable[K]:
    ...


def range(start: int, stop: int | None=None, step: int | None=None) -> t.Iterator[int]:
    ...
