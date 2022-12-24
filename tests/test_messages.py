import numpy as np
import pytest
import inspect
import typing
from itertools import product
from enum import Enum

from k2000.definitions import Button
from k2000.messages import (
    SysexMessage,
    Panel,
    ButtonEvent,
    ButtonEventType,
    __ALL_MESSAGE_TYPES,
    Load,
    Write,
    K2_HEADER,
    K2_FOOTER,
    ScreenReply,
)

RANGES_PER_PARAMETER_NAME = {
    "bank": [1, 9, 127],
    "newbank": [1, 9, 127],
    "idno": [0, 2**14 - 1],
    "newid": [0, 2**14 - 1],
    "offset": [0, 2**21 - 1],
    "size": [0, 2**21 - 1],
    "alpha_wheel_clicks": [-64, 63],
}


def get_possible_values_for_parameter(klass, parameter: inspect.Parameter):
    if parameter.name == "self":
        return None

    if typing.get_origin(parameter.annotation) is list:
        if len(typing.get_args(parameter.annotation)) != 1:
            raise NotImplementedError()

        contained_type = typing.get_args(parameter.annotation)[0]

        return [
            [contained_type(*args)] for args in get_arg_lists_for_klass_constructor(contained_type)
        ]
    elif issubclass(parameter.annotation, Enum):
        return list(parameter.annotation)
    elif parameter.annotation is bool:
        return [True, False]
    elif parameter.annotation is int:
        return RANGES_PER_PARAMETER_NAME[parameter.name]
    elif parameter.annotation is str:
        return ["", "Hello"]
    elif parameter.annotation is bytes:
        return [b"", b"12345"]
    else:
        raise NotImplementedError(
            f"Not sure how to generate training data for {klass.__name__} "
            f"parameter named {parameter.name} with type: {parameter.annotation}."
        )


def get_arg_lists_for_klass_constructor(klass):
    signature = inspect.signature(klass.__init__)

    param_name_to_values = {}
    is_empty = len(set(signature.parameters.keys()) - {"self", "args", "kwargs"}) == 0
    if is_empty:
        return [[]]

    for parameter in signature.parameters.values():
        values = get_possible_values_for_parameter(klass, parameter)
        if not values:
            continue
        param_name_to_values[parameter.name] = values

    arglists = list(product(*param_name_to_values.values()))
    return arglists


def generate_tests(klass):
    return [
        pytest.param(klass, args, id=f"{klass.__name__}({', '.join([str(x) for x in args])})")
        for args in get_arg_lists_for_klass_constructor(klass)
    ]


def test_panel_roundtrip():
    original = Panel(ButtonEvent.press(Button.CursorUp))
    assert Panel.decode(original.encode()) == original
    assert original.encode() == b"\xf0\x07\x00x\x14\t\x10@\x08\x10@\xf7"
    assert Panel.decode(b"\xf0\x07\x00x\x14\t\x10@\x08\x10@\xf7") == original

    assert SysexMessage.decode(original.encode()) == original


@pytest.mark.parametrize("klass", set(__ALL_MESSAGE_TYPES))
def test_all_sysex_messages_have_message_types(klass):
    assert hasattr(klass, "_msg_type_int")
    assert klass._msg_type_int >= 0
    assert klass._msg_type_int < 128


@pytest.mark.parametrize("message_type", set(range(0, 0x1A)) - {0x12, 0x13})
def test_all_message_types_represented(message_type: int):
    assert message_type in set([m._msg_type_int for m in __ALL_MESSAGE_TYPES])


def test_no_message_types_duplicated():
    assert len(set([m._msg_type_int for m in __ALL_MESSAGE_TYPES])) == len(set(__ALL_MESSAGE_TYPES))


@pytest.mark.parametrize(
    "klass,args",
    sum([list(generate_tests(klass)) for klass in set(__ALL_MESSAGE_TYPES)], []),
)
def test_roundtrip(klass, args):
    original = klass(*args)
    roundtripped = SysexMessage.decode(original.encode())
    assert isinstance(roundtripped, klass)
    assert original == roundtripped


@pytest.mark.parametrize(
    "klass,args",
    sum([list(generate_tests(klass)) for klass in [Load, Write]], []),
)
def test_roundtrip_bad_checksum(klass, args):
    original = klass(*args)
    encoded = bytearray(original.encode())
    # Change the checksum of a correctly-encoded message:
    encoded[-2] += 1
    with pytest.raises(ValueError):
        klass.decode(bytes(encoded))


def test_bad_packet():
    with pytest.raises(ValueError):
        SysexMessage.decode(b"1234")


def test_non_sysex_validation():
    assert not SysexMessage.has_valid_k2_headers(b"1234")
    assert not SysexMessage.has_valid_k2_headers(b"12345678")
    assert not SysexMessage.has_valid_k2_headers(K2_HEADER + b"blahblahblah")
    assert SysexMessage.has_valid_k2_headers(K2_HEADER + b"blahblahblah" + K2_FOOTER)


def test_incorrect_header():
    with pytest.raises(ValueError):
        SysexMessage.decode(bytes([1, 2, 3, 4]) + bytes([0x20]) + K2_FOOTER)


def test_incorrect_footer():
    with pytest.raises(ValueError):
        SysexMessage.decode(K2_HEADER + bytes([0x20]) + bytes([0x01]))


def test_unimplemented_message_type():
    with pytest.raises(NotImplementedError):
        SysexMessage.decode(K2_HEADER + bytes([0x20]) + K2_FOOTER)


def test_screen_string_decode():
    assert str(ScreenReply(data=b"Some random string")) == "Some random string"


def test_screen_all_text_decode():
    assert str(ScreenReply(data=b" " * 321)) == "\n".join([" " * 40 for _ in range(8)])


def test_screen_all_text_decode_fails():
    with pytest.raises(TypeError):
        str(ScreenReply(data=b" " * 2561))


def test_screen_all_graphics_decode():
    assert ScreenReply(data=b" " * 2561).to_pixel_array().shape == (240, 64)


def test_screen_all_graphics_decode_fails():
    with pytest.raises(TypeError):
        ScreenReply(data=b" " * 321).to_pixel_array()


def test_screen_all_graphics_encode_fails():
    with pytest.raises(ValueError):
        ScreenReply.from_pixel_array(np.zeros((250, 65)))


@pytest.mark.parametrize("clicks", [-65, 64])
def test_button_event_validation(clicks: int):
    with pytest.raises(ValueError):
        ButtonEvent(ButtonEventType.AlphaWheel, Button.Cancel, alpha_wheel_clicks=clicks)


def test_button_event_decoding():
    # Just to get to 100% coverage. This should never happen.
    with pytest.raises(ValueError):
        ButtonEvent.decode(b"1234")
