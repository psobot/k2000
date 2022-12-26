import re
import os
import pytest
import numpy as np
from typing import Optional
from unittest.mock import MagicMock, Mock
import PIL.Image

import rtmidi

from k2000.client import K2BaseClient
from k2000.messages import (
    Dir,
    Info,
    Load,
    ScreenReply,
    K2_FOOTER,
    DataAcknowledged,
    DataNotAcknowledged,
)
from k2000.definitions import ObjectType, Button, EncodingFormat


def camel2snake(camel_input: str) -> str:
    words = re.findall(
        r"[A-Z]?[a-z]+|[A-Z]{2,}(?=[A-Z][a-z]|\d|\W|$)|\d+|[A-Z]{2,}|[A-Z]$", camel_input
    )
    return "_".join(map(str.lower, words))


@pytest.fixture
def midi_in():
    midi_in = Mock(spec=rtmidi.MidiIn)
    midi_in.get_ports = MagicMock(return_value=["foobar"])
    midi_in.index = MagicMock(return_value=0)
    return midi_in


@pytest.fixture
def midi_out():
    midi_in = Mock(spec=rtmidi.MidiOut)
    midi_in.get_ports = MagicMock(return_value=["foobar"])
    midi_in.index = MagicMock(return_value=0)
    return midi_in


@pytest.mark.parametrize("midi_identifier", [None, "Foobar"])
def test(midi_identifier: Optional[str], midi_in, midi_out):
    client = K2BaseClient(midi_identifier=midi_identifier, midi_in=midi_in, midi_out=midi_out)
    assert client
    assert "foobar" in repr(client)


def test_no_interfaces(midi_in, midi_out):
    midi_in.get_ports = MagicMock(return_value=[])
    midi_out.get_ports = MagicMock(return_value=[])
    with pytest.raises(RuntimeError):
        assert K2BaseClient(midi_in=midi_in, midi_out=midi_out)


def test_missing_identifier(midi_in, midi_out):
    with pytest.raises(RuntimeError):
        assert K2BaseClient(midi_identifier="does not exist", midi_in=midi_in, midi_out=midi_out)


@pytest.mark.parametrize("midi_identifier", [None, "Foobar"])
def test_checks_for_bidirectional(midi_identifier: Optional[str], midi_in, midi_out):
    midi_out.get_ports = MagicMock(return_value=["foobar2"])

    with pytest.raises(RuntimeError):
        K2BaseClient(midi_identifier=midi_identifier, midi_in=midi_in, midi_out=midi_out)


@pytest.mark.parametrize("midi_identifier", [None, "Foobar"])
def test_error_on_multiple_matches(midi_identifier: Optional[str], midi_in, midi_out):
    midi_in.get_ports = MagicMock(return_value=["foobar2", "foobar3"])
    midi_out.get_ports = MagicMock(return_value=["foobar2", "foobar3"])

    with pytest.raises(RuntimeError):
        K2BaseClient(midi_identifier=midi_identifier, midi_in=midi_in, midi_out=midi_out)


def test_send_and_receive_message(midi_in, midi_out):
    midi_in.get_message = Mock(
        side_effect=[
            (b"1234", 1.2),
            (Info(ObjectType.Program, 1, 123, False, "Nothing").encode(), 0.0),
            None,
        ]
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    response = client._send_and_receive(Dir(ObjectType.Program, 1))
    assert isinstance(response, Info)


def test_send_and_receive_message_timeout(midi_in, midi_out):
    midi_in.get_message = Mock(side_effect=[None])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    with pytest.raises(TimeoutError):
        client._send_and_receive(Dir(ObjectType.Program, 1), timeout=0.0)


def test_send_and_receive_message_exceptions(midi_in, midi_out):
    # Provide a half-done message:
    encoded = Info(ObjectType.Program, 1, 123, False, "Bad").encode()
    encoded = encoded[:-6] + K2_FOOTER

    midi_in.get_message = Mock(side_effect=[(encoded, 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    with pytest.raises(ValueError):
        client._send_and_receive(Dir(ObjectType.Program, 1), timeout=0.0)


def test_is_connected(midi_in, midi_out):
    midi_in.get_message = Mock(
        side_effect=[
            (ScreenReply.from_screen_contents("Hello, world!").encode(), 0.0),
        ]
        + [None] * 1000
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    assert client.is_connected
    # Second time through, our MIDI mock will reply with None:
    assert not client.is_connected


def test_get_graphics(midi_in, midi_out):
    midi_in.get_message = Mock(
        side_effect=[(ScreenReply.from_pixel_array(np.zeros((240, 64))).encode(), 0.0)]
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    assert client.get_graphics().shape == (240, 64)


def test_get_parameter_name(midi_in, midi_out):
    midi_in.get_message = Mock(side_effect=[(ScreenReply.from_text("Name").encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    assert client.get_current_parameter_name() == "Name"


def test_get_parameter_value(midi_in, midi_out):
    midi_in.get_message = Mock(side_effect=[(ScreenReply.from_text("Value").encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    assert client.get_current_parameter_value() == "Value"


@pytest.mark.parametrize("button", list(Button))
def test_press_button(button: Button, midi_in, midi_out):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    client.press_button(button)
    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x14\t" + bytes([button.value]) + b"@\x08" + bytes([button.value]) + b"@\xf7"
    )


@pytest.mark.parametrize("button", [b for b in Button if "Number" not in b.name])
def test_press_button_separate_method(button: Button, midi_in, midi_out):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    method_name = camel2snake(
        button.name.replace("Cursor", "").replace("Soft", "").replace("Effects", "Effect")
    )
    assert hasattr(client, method_name)
    getattr(client, method_name)()

    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x14\t" + bytes([button.value]) + b"@\x08" + bytes([button.value]) + b"@\xf7"
    )


@pytest.mark.parametrize("button_name", ["SoftYes", "SoftNo"])
def test_press_button_separate_method_duplicates(button_name: str, midi_in, midi_out):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    button_value = getattr(Button, button_name).value
    method_name = camel2snake(button_name.replace("Cursor", "").replace("Soft", ""))
    assert hasattr(client, method_name)
    getattr(client, method_name)()

    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x14\t" + bytes([button_value]) + b"@\x08" + bytes([button_value]) + b"@\xf7"
    )


@pytest.mark.parametrize(
    "input,expected",
    [
        (1, b"\t\x01@\x08\x01@"),
        (10, b"\t\x01@\x08\x01@\t\x00@\x08\x00@"),
        (11, b"\t\x01@\t\x01@\x08\x01@"),
        (-11, b"\t\x0a@\x08\x0a@\t\x01@\t\x01@\x08\x01@"),
        (1.0, b"\t\x01@\x08\x01@"),
        (10.0, b"\t\x01@\x08\x01@\t\x00@\x08\x00@"),
        (11.0, b"\t\x01@\t\x01@\x08\x01@"),
        (-11.0, b"\t\x0a@\x08\x0a@\t\x01@\t\x01@\x08\x01@"),
        ("1", b"\t\x01@\x08\x01@"),
        ("1.0", b"\t\x01@\x08\x01@"),
    ],
)
def test_number(input: int, expected: bytes, midi_in, midi_out):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    client.number(input)
    midi_out.send_message.assert_called_with(b"\xf0\x07\x00x\x14" + expected + b"\xf7")


@pytest.mark.parametrize("input", [1.1234, "1.1234", None, [1.234]])
def test_number_fail(input: int, midi_in, midi_out):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    with pytest.raises(TypeError):
        client.number(input)


def test_dump(midi_in, midi_out):
    sent_response = Load(ObjectType.Program, 123, 0, EncodingFormat.Nibblized, b" " * 234)
    midi_in.get_message = Mock(side_effect=[(sent_response.encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    received_response = client.dump(ObjectType.Program, 123, 0, 234)
    assert received_response == sent_response
    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x00\x01\x04\x00{\x00\x00\x00\x00\x01j\x01\xf7"
    )


def test_dir(midi_in, midi_out):
    sent_response = Info(ObjectType.Program, 123, 234, False, "Foobar")
    midi_in.get_message = Mock(side_effect=[(sent_response.encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    received_response = client.dir(ObjectType.Program, 123)
    assert received_response == sent_response
    midi_out.send_message.assert_called_with(b"\xf0\x07\x00x\x04\x01\x04\x00{\xf7")


def test_load(midi_in, midi_out):
    sent_response = DataAcknowledged(ObjectType.Program, 123, 2, 2)
    midi_in.get_message = Mock(side_effect=[(sent_response.encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    received_response = client.load(ObjectType.Program, 123, b" " * 2, offset=2)
    assert received_response == sent_response
    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x01\x01\x04\x00{\x00\x00\x02\x00\x00\x02\x01\x00@ `\xf7"
    )


def test_new(midi_in, midi_out):
    sent_response = Info(ObjectType.Program, 123, 234, True, "Foo")
    midi_in.get_message = Mock(side_effect=[(sent_response.encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    received_response = client.new(ObjectType.Program, 123, 234, create_ram_copy=True, name="Foo")
    assert received_response == sent_response
    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\x06\x01\x04\x00{\x00\x01j\x01Foo\x00\xf7"
    )


def test_write(midi_in, midi_out):
    sent_response = DataAcknowledged(ObjectType.Program, 123, 0, 4)
    midi_in.get_message = Mock(side_effect=[(sent_response.encode(), 0.0)])
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    received_response = client.write(ObjectType.Program, 123, "MyProgram", b"1234")
    assert received_response == sent_response
    midi_out.send_message.assert_called_with(
        b"\xf0\x07\x00x\t\x01\x04\x00{\x00\x00\x04\x00MyProgram\x00\x01\x03\tHf4n\xf7"
    )


@pytest.mark.parametrize("object_type", list(ObjectType))
@pytest.mark.parametrize("method", ["items", "__getitem__", "values"])
def test_object_proxy_get(object_type: ObjectType, method, midi_in, midi_out):
    midi_in.get_message = Mock(
        side_effect=sum(
            [
                # Yield Info and Load messages for every object in order:
                [
                    (
                        Info(object_type, idno, idno - 1, False, f"Test Object {idno}").encode(),
                        0.0,
                    ),
                    (
                        Load(
                            object_type,
                            idno,
                            0,
                            EncodingFormat.BitStream,
                            f"Data {idno}".encode("ascii"),
                        ).encode(),
                        0.0,
                    ),
                ]
                for idno in range(1, 1000)
            ],
            [],
        )
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)

    proxy = getattr(client, camel2snake(object_type.name) + "s")
    assert list(proxy.keys()) == list(range(1, 1000))

    if method == "items":
        all_items = list(proxy.items())
        assert len(all_items) == len(proxy.keys())
    elif method == "__getitem__":
        all_items = [(i, proxy[i]) for i in proxy.keys()]
    elif method == "values":
        all_items = [(i + 1, value) for i, value in enumerate(proxy.values())]

    for i, value in all_items:
        if i == 1:
            assert value is None
        else:
            name, data = value
            assert name == f"Test Object {i}"
            assert data == f"Data {i}".encode("ascii")


@pytest.mark.parametrize("object_type", list(ObjectType))
@pytest.mark.parametrize(
    "input,exception_type", [("Foobar", TypeError), (1234, ValueError), (-123, ValueError)]
)
def test_object_proxy_read_key_validation(
    object_type: ObjectType, input, exception_type, midi_in, midi_out
):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)

    proxy = getattr(client, camel2snake(object_type.name) + "s")
    with pytest.raises(exception_type):
        proxy[input]


@pytest.mark.parametrize("object_type", list(ObjectType))
def test_object_proxy_set(object_type: ObjectType, midi_in, midi_out):
    midi_in.get_message = Mock(
        side_effect=[
            # Yield DataAcknowledged messages for every object in order, except the first.
            (
                DataAcknowledged(object_type, idno, 0, len(f"Data {idno}".encode("ascii"))).encode()
                if idno > 1
                else DataNotAcknowledged(
                    object_type,
                    idno,
                    0,
                    len(f"Data {idno}".encode("ascii")),
                    DataNotAcknowledged.ErrorCode.ObjectNotFound,
                ).encode(),
                0.0,
            )
            for idno in range(1, 1000)
        ]
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)

    proxy = getattr(client, camel2snake(object_type.name) + "s")
    assert list(proxy.keys()) == list(range(1, 1000))

    for i in proxy.keys():
        if i == 1:
            with pytest.raises(RuntimeError):
                proxy[i] = (f"Test Object {i}", f"Data {i}".encode("ascii"))
        else:
            proxy[i] = (f"Test Object {i}", f"Data {i}".encode("ascii"))


@pytest.mark.parametrize("object_type", list(ObjectType))
@pytest.mark.parametrize(
    "input,value,exception_type",
    [
        ("Foobar", ("Foo", b"Bar"), TypeError),
        (1234, ("Foo", b"Bar"), ValueError),
        (-123, ("Foo", b"Bar"), ValueError),
        (123, "Foo", TypeError),
        (123, b"Bar", TypeError),
        (123, ("Foo", "Bar"), TypeError),
        (123, (b"Foo", b"Bar"), TypeError),
    ],
)
def test_object_proxy_write_key_validation(
    object_type: ObjectType, input, value, exception_type, midi_in, midi_out
):
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)

    proxy = getattr(client, camel2snake(object_type.name) + "s")
    with pytest.raises(exception_type):
        proxy[input] = value


def test_screenshot(midi_in, midi_out):
    PIXEL_TOLERANCE = 0.10 * 255
    EXPECTED_TEXT_CONTENTS = [
        "ProgramMode    Xpose:0ST   <>Channel:1  ",
        "                    998 Choral Sleigh   ",
        "KeyMap Info         999 Pad Nine        ",
        " Grand Piano          1 Acoustic Piano  ",
        " Syn Piano            2 Stage Piano     ",
        "                      3 BriteGrand      ",
        "                      4 ClassicPiano&Vox",
        "Octav- Octav+ Panic  Sample Chan-  Chan+",
    ]
    with open(os.path.join(os.path.dirname(__file__), "good_graphics_layer_packed.bin"), "rb") as f:
        EXPECTED_GRAPHICS_CONTENTS = np.unpackbits(np.frombuffer(f.read(), np.uint8))
        EXPECTED_GRAPHICS_CONTENTS = EXPECTED_GRAPHICS_CONTENTS.reshape(240, -1)
    midi_in.get_message = Mock(
        side_effect=[
            # Yield ScreenReply messages containing both image data and text data:
            (ScreenReply.from_pixel_array(EXPECTED_GRAPHICS_CONTENTS).encode(), 0.0),
            (ScreenReply.from_screen_contents("\n".join(EXPECTED_TEXT_CONTENTS)).encode(), 0.0),
        ]
    )
    client = K2BaseClient(midi_in=midi_in, midi_out=midi_out)
    image = client.screenshot()
    assert image is not None
    expected = PIL.Image.open(os.path.join(os.path.dirname(__file__), "expected_screenshot.png"))
    assert image.size == expected.size
    for i, (actual_pixel, expected_pixel) in enumerate(zip(image.getdata(), expected.getdata())):
        actual_r, actual_g, actual_b = actual_pixel[:3]
        expected_r, expected_g, expected_b = expected_pixel[:3]
        assert abs(actual_r - expected_r) < PIXEL_TOLERANCE, f"Red pixel mismatch at index {i}!"
        assert abs(actual_g - expected_g) < PIXEL_TOLERANCE, f"Green pixel mismatch at index {i}!"
        assert abs(actual_b - expected_b) < PIXEL_TOLERANCE, f"Blue pixel mismatch at index {i}!"
