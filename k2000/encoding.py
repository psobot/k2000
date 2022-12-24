from typing import Iterable, Union
from functools import partial

from k2000.utils import grouper


def encode_n(value: Union[int, bytes], num_bytes: int, n: int) -> bytes:
    """
    Given a single byte value on [0, 255], return a bytestring
    of length `num_bytes` that contains the value packed into
    successive n-bit chunks, right-aligned in each byte.
    """
    if isinstance(value, int):
        if value < 0:
            raise ValueError(
                f"Can't encode negative value {repr(value)} in {num_bytes} {n}-bit bytes."
            )
        if value >= (2 ** (n * num_bytes)):
            raise ValueError(f"Can't encode value {repr(value)} in {num_bytes} {n}-bit bytes.")
    elif isinstance(value, bytes):
        value = int.from_bytes(value, "big")
    else:
        raise TypeError(
            f"Expected either int or bytes to convert to {n}-bit format, but got: {type(value)}!"
        )
    return bytes([(value >> (n * i)) & ((2**n) - 1) for i in reversed(range(num_bytes))])


encode = {i: partial(encode_n, n=i) for i in range(1, 8)}


def bit_array_to_int(bit_array: Iterable[bool]) -> int:
    value = 0
    for i, bit in enumerate(reversed(list(bit_array))):
        value |= int(bit) << i
    return value


def decode_n(value: bytes, n: int) -> bytes:
    """
    Given an n-bit encoded bytestring, return an 8-bit encoded bytestring.
    """
    # Yes, this creates a Python object for every bit of the input data.
    # Could this be more efficient? For sure.
    bits = []
    for input_byte in value:
        if input_byte >> n != 0:
            raise ValueError(
                f"decode_n(n={n}) received a byte with bits "
                f"set above the {n}th: {bin(input_byte)}"
            )
        for i in reversed(range(n)):
            bits.append(bool(input_byte & (1 << i)))

    while len(bits) % 8 != 0:
        bits.insert(0, False)

    return bytes([bit_array_to_int(bit_array) for bit_array in list(grouper(bits, 8))])


decode = {i: partial(decode_n, n=i) for i in range(1, 8)}
