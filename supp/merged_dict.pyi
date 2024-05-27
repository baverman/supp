import typing as t

KT = t.TypeVar('KT')
VT = t.TypeVar('VT')


class MergedDict(t.Mapping[KT, VT]):
    def __init__(self, *dicts: t.Mapping[KT, VT]) -> None:
        ...

    def __getitem__(self, key: KT) -> VT:
        ...

    def __iter__(self) -> t.Iterator[KT]:
        ...

    def __len__(self) -> int:
        ...
