import pytest
from typing import Any
from k2000.encoding import encode, decode


@pytest.mark.parametrize(
    "input,num_bytes,expected",
    [
        (1, 1, b"\x01"),
        (1, 2, b"\x00\x01"),
        (128, 2, b"\x01\x00"),
        (16_384, 3, b"\x01\x00\x00"),
        (2 ** (7 * 1) - 1, 1, b"\x7F"),
        (2 ** (7 * 2) - 1, 2, b"\x7F\x7F"),
        (2 ** (7 * 3) - 1, 3, b"\x7F\x7F\x7F"),
    ],
)
def test_7bit_encoding(input: int, num_bytes: int, expected: bytes):
    assert encode[7](input, num_bytes) == expected
    assert int.from_bytes(decode[7](encode[7](input, num_bytes)), "big") == input


@pytest.mark.parametrize(
    "input,num_bytes,exception",
    [
        (-1, 1, ValueError),
        ("1", 1, TypeError),
        ("foo", 1, TypeError),
        (2 ** (7 * 1), 1, ValueError),
        (2 ** (7 * 2), 2, ValueError),
        (2 ** (7 * 3), 3, ValueError),
    ],
)
def test_7bit_encoding_throws_exception(input: Any, num_bytes: int, exception):
    with pytest.raises(exception):
        encode[7](input, num_bytes)


@pytest.mark.parametrize("input,exception", [(b"\xFF", ValueError)])
def test_7bit_decoding_throws_exception(input: Any, exception):
    with pytest.raises(exception):
        decode[7](input)
