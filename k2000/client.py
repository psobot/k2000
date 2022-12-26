import time
from typing import cast, Optional, Iterable, Tuple, Union

import rtmidi
import numpy as np

from k2000.definitions import ObjectType, Button, ButtonEventType, EncodingFormat, WriteMode
from k2000.messages import (
    Dump,
    Load,
    Dir,
    Info,
    New,
    AllText,
    ScreenReply,
    SysexMessage,
    GetGraphics,
    Panel,
    ButtonEvent,
    ParameterName,
    ParameterValue,
    DataAcknowledged,
    DataNotAcknowledged,
    Write,
)


class K2BaseClient(object):
    """A client object that can communicate with an attached
    K2-series synthesizer connected over MIDI."""

    def __init__(
        self,
        midi_identifier: Optional[str] = None,
        midi_out: Optional[rtmidi.MidiOut] = None,
        midi_in: Optional[rtmidi.MidiIn] = None,
    ):
        self.midi_out = midi_out or rtmidi.MidiOut()
        self.midi_in = midi_in or rtmidi.MidiIn(queue_size_limit=8192)

        self.midi_in.ignore_types(sysex=False)

        in_port_names = set(self.midi_in.get_ports())
        out_port_names = set(self.midi_out.get_ports())

        if not in_port_names or not out_port_names:
            raise RuntimeError("No MIDI interface found.")

        bidirectional_port_names = in_port_names & out_port_names
        if not bidirectional_port_names:
            raise RuntimeError("No bidirectional MIDI interface found. Is one connected?")

        if midi_identifier:
            bidirectional_port_names = set(
                [
                    port_name
                    for port_name in bidirectional_port_names
                    if midi_identifier.lower() in port_name.lower()
                ]
            )

        if not bidirectional_port_names:
            raise RuntimeError(
                "No bidirectional MIDI interface found "
                f"matching {repr(midi_identifier)}. Is one connected?"
            )

        if len(bidirectional_port_names) == 1:
            port_name = bidirectional_port_names.pop()
        else:
            if midi_identifier:
                matching = f" matching {repr(midi_identifier)}"
            else:
                matching = ""
            raise RuntimeError(
                f"More than one bidirectional MIDI interface found{matching}, "
                f"but no midi_identifier was passed to the {self.__class__.__name__} constructor. "
                f"{'Matching' if midi_identifier else 'Available'} interfaces are: "
                f"{', '.join(bidirectional_port_names)}"
            )

        self.port_name = port_name

        self.midi_out.open_port(self.midi_out.get_ports().index(self.port_name))
        self.midi_in.open_port(self.midi_in.get_ports().index(self.port_name))

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__module__}.{self.__class__.__qualname__} "
            f"connected to {repr(self.port_name)} at {hex(id(self))}>"
        )

    def _send_and_receive(self, message: SysexMessage, timeout: float = 1.0) -> "SysexMessage":
        response_classes = tuple(message._response_classes or [SysexMessage])

        self.midi_out.send_message(message.encode())

        exception = None
        for _ in range(max(1, int(timeout / 0.01))):
            response = self.midi_in.get_message()
            if response is not None:
                response_data, _timestamp = response

                if SysexMessage.has_valid_k2_headers(response_data):
                    try:
                        decoded = SysexMessage.decode(response_data)
                        if isinstance(decoded, response_classes):
                            return decoded
                    except Exception as e:
                        exception = e
            time.sleep(0.01)
        else:
            if exception:
                raise exception
            raise TimeoutError(
                "Did not get a response from the attached "
                f"device within the timeout ({timeout:.2f} seconds)."
            )

    @property
    def is_connected(self) -> bool:
        """
        Ensure that the attached K2 synthesizer is responding.
        This sends a request to get the screen contents.
        """
        try:
            return self.get_screen_text(timeout=0.1) is not None
        except TimeoutError:
            return False

    @property
    def programs(self):
        return K2ObjectProxy(self, ObjectType.Program)

    @property
    def keymaps(self):
        return K2ObjectProxy(self, ObjectType.Keymap)

    @property
    def effects(self):
        return K2ObjectProxy(self, ObjectType.Effect)

    @property
    def songs(self):
        return K2ObjectProxy(self, ObjectType.Song)

    @property
    def setups(self):
        return K2ObjectProxy(self, ObjectType.Setup)

    @property
    def soundblocks(self):
        return K2ObjectProxy(self, ObjectType.Soundblock)

    @property
    def velocity_maps(self):
        return K2ObjectProxy(self, ObjectType.VelocityMap)

    @property
    def pressure_maps(self):
        return K2ObjectProxy(self, ObjectType.PressureMap)

    @property
    def quick_access_banks(self):
        return K2ObjectProxy(self, ObjectType.QuickAccessBank)

    @property
    def intonation_tables(self):
        return K2ObjectProxy(self, ObjectType.IntonationTable)

    def get_screen_text(self, timeout: float = 1.0) -> str:
        """
        Get the current contents of the text layer of the screen.
        """
        return str(self._send_and_receive(AllText(), timeout))

    def get_graphics(self, timeout: float = 1.0) -> np.ndarray:
        """
        Get the current contents of the graphics layer of the screen.
        """
        return cast(ScreenReply, self._send_and_receive(GetGraphics(), timeout)).to_pixel_array()

    def get_current_parameter_name(self, timeout: float = 1.0) -> str:
        return str(self._send_and_receive(ParameterName(), timeout))

    def get_current_parameter_value(self, timeout: float = 1.0) -> str:
        return str(self._send_and_receive(ParameterValue(), timeout))

    def press_button(self, button: Button):
        """
        Send a single button press - down, followed by up - for the provided button.

        If sending multiple button presses, consider using `press_buttons` instead.
        """
        self.midi_out.send_message(
            Panel(
                [
                    ButtonEvent(ButtonEventType.Down, button),
                    ButtonEvent(ButtonEventType.Up, button),
                ]
            ).encode()
        )

    def press_buttons(self, buttons: Iterable[Button]):
        """
        Send a sequence of button presses for each provided button.
        If the same button is provided multiple times, in a row, multiple
        `Down` events will be sent, followed by only one `Up`.
        """
        events = []
        for button, next_button in zip(buttons, buttons[1:] + [None]):
            events.append(ButtonEvent(ButtonEventType.Down, button))
            if button != next_button:
                events.append(ButtonEvent(ButtonEventType.Up, button))
        self.midi_out.send_message(Panel(events).encode())

    def number(self, number: int):
        """
        Type a number into the attached K2.

        If the number contains multiple digits, multiple button presses will be sent.
        """
        if isinstance(number, str):
            number = float(number)
        if isinstance(number, float):
            if number.is_integer():
                number = int(number)
            else:
                raise TypeError("number() can only accept integers!")

        buttons = []

        if number < 0:
            buttons.append(Button.PlusMinus)
            number *= -1

        buttons.extend([getattr(Button, f"Number{digit}") for digit in str(number)])

        self.press_buttons(buttons)

    def plus_minus(self):
        self.press_button(Button.PlusMinus)

    def cancel(self):
        self.press_button(Button.Cancel)

    def clear(self):
        self.press_button(Button.Clear)

    def enter(self):
        self.press_button(Button.Enter)

    def plus(self):
        self.press_button(Button.Plus)

    def minus(self):
        self.press_button(Button.Minus)

    def plus_and_minus(self):
        self.press_button(Button.PlusAndMinus)

    def chan_bank_inc(self):
        self.press_button(Button.ChanBankInc)

    def chan_bank_dec(self):
        self.press_button(Button.ChanBankDec)

    def chan_bank_inc_dec(self):
        self.press_button(Button.ChanBankIncDec)

    def left(self):
        self.press_button(Button.CursorLeft)

    def right(self):
        self.press_button(Button.CursorRight)

    def left_right(self):
        self.press_button(Button.CursorLeftRight)

    def up(self):
        self.press_button(Button.CursorUp)

    def down(self):
        self.press_button(Button.CursorDown)

    def a(self):
        self.press_button(Button.SoftA)

    def b(self):
        self.press_button(Button.SoftB)

    def c(self):
        self.press_button(Button.SoftC)

    def d(self):
        self.press_button(Button.SoftD)

    def e(self):
        self.press_button(Button.SoftE)

    def f(self):
        self.press_button(Button.SoftF)

    def ab(self):
        self.press_button(Button.SoftAB)

    def cd(self):
        self.press_button(Button.SoftCD)

    def ef(self):
        self.press_button(Button.SoftEF)

    def yes(self):
        self.press_button(Button.SoftYes)

    def no(self):
        self.press_button(Button.SoftNo)

    def edit(self):
        self.press_button(Button.Edit)

    def exit(self):
        self.press_button(Button.Exit)

    def program(self):
        self.press_button(Button.Program)

    def setup(self):
        self.press_button(Button.Setup)

    def quick_access(self):
        self.press_button(Button.QuickAccess)

    def effect(self):
        self.press_button(Button.Effects)

    def midi(self):
        self.press_button(Button.MIDI)

    def master(self):
        self.press_button(Button.Master)

    def song(self):
        self.press_button(Button.Song)

    def disk(self):
        self.press_button(Button.Disk)

    def dump(self, type: ObjectType, idno: int, offset: int = 0, size: int = 2**21 - 1) -> Load:
        """
        Get the data bytes for an object, identified by type and idno.
        `offset` and `size` specify the range of data to be fetched, as little as one byte.
        """
        assert Load in Dump._response_classes
        return cast(
            Load, self._send_and_receive(Dump(type, idno, offset, size, EncodingFormat.BitStream))
        )

    def dir(self, type: ObjectType, idno: int) -> Info:
        """
        Get the metadata (name, size, and storage) for an object, identified by type and idno.
        """
        assert Info in Dir._response_classes
        return cast(Info, self._send_and_receive(Dir(type, idno)))

    def load(
        self, type: ObjectType, idno: int, data: bytes, offset: int = 0
    ) -> Union[DataAcknowledged, DataNotAcknowledged]:
        """
        Set the data bytes for an existing object, identified by type and idno.
        """
        return self._send_and_receive(Load(type, idno, offset, EncodingFormat.BitStream, data))

    def new(self, type: ObjectType, idno: int, size: int, create_ram_copy: bool, name: str) -> Info:
        """
        Create a new object.

        The object's data will not be initialized to any default values.

        If 'idno' is zero, the first available object ID number will be assigned.
        If 'create_ram_copy' is False, the request will fail if the object exists.
        If 'create_ram_copy' is True, and the object exists in ROM, a RAM copy will be made.
        If 'create_ram_copy' is True, and the object exists in RAM, no action is taken.
        """
        return cast(Info, self._send_and_receive(New(type, idno, size, create_ram_copy, name)))

    def write(
        self, type: ObjectType, idno: int, name: str, data: bytes
    ) -> Union[DataAcknowledged, DataNotAcknowledged]:
        """
        Write an entire object's data directly into the database.

        This method first deletes any object already existing at the same
        type/ID. If no RAM object currently exists there, a new
        one will be allocated and the data will be written into it.

        The object name will be set if the 'name' string is non-null.
        """
        return self._send_and_receive(
            Write(type, idno, WriteMode.WriteToExactIDNumber, name, EncodingFormat.BitStream, data)
        )


class K2ObjectProxy:
    """
    A proxy object that acts like a list (or dict with keys).
    """

    def __init__(self, client: K2BaseClient, type: ObjectType):
        self.client = client
        self.type = type

    def __getitem__(self, key: int) -> Optional[Tuple[str, bytes]]:
        if not isinstance(key, int):
            raise TypeError("Key must be an integer!")

        if key > 1000 or key < 1:
            raise ValueError("ID number must be between 1 and 999, inclusive.")

        info = self.client.dir(self.type, key)
        if info.size != 0:
            load = self.client.dump(self.type, key)
            return (info.name, load.data)
        return None

    def __setitem__(self, key: int, value: Tuple[str, bytes]):
        if not isinstance(key, int):
            raise TypeError("Key must be an integer!")

        if key > 1000 or key < 1:
            raise ValueError("ID number must be between 1 and 999, inclusive.")

        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], str)
            or not isinstance(value[1], bytes)
        ):
            raise TypeError("Value must be a tuple of (name: str, data: bytes).")

        name, data = value

        response = self.client.write(self.type, key, name, data)
        if isinstance(response, DataNotAcknowledged):
            raise RuntimeError(f"Could not set {self.type} ID {key}: {response.code.name}")

    def items(self) -> Iterable[Tuple[int, Optional[Tuple[str, bytes]]]]:
        for idno in self.keys():
            yield idno, self[idno]

    def keys(self) -> Iterable[int]:
        return range(1, 1000)

    def values(self) -> Iterable[Optional[Tuple[str, bytes]]]:
        for _, value in self.items():
            yield value


class K2000Client(K2BaseClient):
    """A MIDI interface class to an attached K2000."""


class K2500Client(K2BaseClient):
    """A MIDI interface class to an attached K2500."""


class K2600Client(K2BaseClient):
    """A MIDI interface class to an attached K2600."""
