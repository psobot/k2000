import re
import pytest
import numpy as np
from typing import Optional
from unittest.mock import MagicMock, Mock

import rtmidi

from k2000.client import K2BaseClient
from k2000.messages import Dir, Info, Load, ScreenReply, K2_FOOTER
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
    method_name = camel2snake(button.name.replace("Cursor", "").replace("Soft", ""))
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
