from typing import Optional, Iterable, TypeVar
from itertools import zip_longest


T = TypeVar("T")


def grouper(iterable: Iterable[T], n: int, fillvalue: Optional[T] = None) -> Iterable[Iterable[T]]:
    "Collect data into fixed-length chunks or blocks"
    return zip_longest(*([iter(iterable)] * n), fillvalue=fillvalue)
