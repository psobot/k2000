import math
from enum import Enum
from typing import Dict, List, Type, Optional

from attrs import define, field
import numpy as np

from k2000.definitions import ObjectType, Button, ButtonEventType, EncodingFormat, WriteMode
from k2000.encoding import encode, decode
from k2000.utils import grouper


# Constants for MIDI control
START_OF_SYSTEM_EXCLUSIVE = bytes([0xF0])
KURZWEIL_MANUFACTURER_ID = bytes([0x07])
DEFAULT_DEVICE_ID = bytes([0x00])

# TODO(psobot): does this apply to the K2000 and K2600 as well?
K2500_PRODUCT_IDENTIFIER = bytes([0x78])
END_OF_SYSTEM_EXCLUSIVE = bytes([0xF7])

K2_HEADER: bytes = (
    START_OF_SYSTEM_EXCLUSIVE
    + KURZWEIL_MANUFACTURER_ID
    + DEFAULT_DEVICE_ID
    + K2500_PRODUCT_IDENTIFIER
)

K2_FOOTER: bytes = END_OF_SYSTEM_EXCLUSIVE
MIN_PACKET_SIZE = len(K2_HEADER) + 1 + len(K2_FOOTER)
_TYPE_MAP: Dict[int, Type["SysexMessage"]] = {}


class SysexMessage:
    """
    A superclass for all Kurzweil K2 sysex messages.
    Probably shouldn't be used directly.
    """

    _msg_type_int: Optional[int] = None
    _response_classes: List[Type["SysexMessage"]] = []

    @classmethod
    def has_valid_k2_headers(cls, data: bytes) -> bool:
        if len(data) < MIN_PACKET_SIZE:
            return False
        for expected, actual in zip(data[: len(K2_HEADER)], K2_HEADER):
            if expected != actual:
                return False
        for expected, actual in zip(data[-len(K2_FOOTER) :], K2_FOOTER):
            if expected != actual:
                return False

        return True

    @classmethod
    def decode(cls, data: bytes) -> "SysexMessage":
        """
        Given a message as raw bytes, return a SysexMessage subclass
        that represents this message.
        """

        if len(data) < MIN_PACKET_SIZE:
            raise ValueError(
                "Received MIDI message is too small to contain a "
                f"full Kurzweil packet: expected at least {MIN_PACKET_SIZE:,} "
                f"bytes, but got only {len(data):,}."
            )
        for expected, actual in zip(data[: len(K2_HEADER)], K2_HEADER):
            if expected != actual:
                raise ValueError(
                    "SysexMessage has invalid header: "
                    f"expected {K2_HEADER!r}, got {data[:len(K2_HEADER)]!r}"
                )
        for expected, actual in zip(data[-len(K2_FOOTER) :], K2_FOOTER):
            if expected != actual:
                raise ValueError(
                    f"SysexMessage has invalid footer: expected {expected!r}, got {actual!r}"
                )

        message_type = data[len(K2_HEADER)]
        klass = _TYPE_MAP.get(message_type, None)
        if not klass:
            raise NotImplementedError(
                f"Don't know how to handle Kurzweil SysEx message of type: {message_type:02x}"
            )

        sub_data = data[len(K2_HEADER) + 1 : -len(K2_FOOTER)]
        try:
            return klass._decode_body(sub_data)
        except Exception as e:
            raise ValueError(
                f"Failed to decode {len(data):,}-byte packet as '{klass.__name__}' message."
            ) from e

    def encode(self) -> bytes:
        """
        Serialize this message to bytes that can be sent on the wire.
        """
        return K2_HEADER + bytes([self._msg_type_int]) + self._encode_body() + K2_FOOTER


class EmptyBody:
    @classmethod
    def _decode_body(cls, data: bytes) -> "SysexMessage":
        assert not data, f"Expected {cls.__name__} message to have no body!"
        return cls()

    def _encode_body(self) -> bytes:
        return b""


@define
class Dump(SysexMessage):
    """
    Requests the K2500 to send a data dump of an object or portion thereof.
    'type' and 'idno' identify the object. 'offs' is the offset from the
    beginning of the object's data and 'size' describes how many bytes
    should be dumped starting from the offset. 'form' indicates how the
    binary data is to transmitted (0=nibblized, 1=bit stream). The
    response is a LOAD message.
    """

    _msg_type_int = 0x00

    type: ObjectType
    idno: int
    offset: int
    size: int
    form: EncodingFormat

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.offset, 3)
            + encode[7](self.size, 3)
            + encode[7](self.form.value, 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        offset = int.from_bytes(decode[7](data[4:7]), "big")
        size = int.from_bytes(decode[7](data[7:10]), "big")
        form = EncodingFormat(data[10])
        return cls(_type, idno, offset, size, form)


@define
class Load(SysexMessage):
    """
    Write data into the specified object, which must exist.
    """

    _msg_type_int = 0x01

    type: ObjectType
    idno: int
    offset: int
    form: EncodingFormat
    data: bytes

    def _encode_body(self):
        if self.form == EncodingFormat.Nibblized:
            encoded_data = encode[4](self.data, int(math.ceil(len(self.data) * 8 / 4)))
        else:
            encoded_data = encode[7](self.data, int(math.ceil(len(self.data) * 8 / 7)))

        checksum = sum(encoded_data) & 0b1111111
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.offset, 3)
            + encode[7](len(self.data), 3)
            + encode[7](self.form.value, 1)
            + encoded_data
            + encode[7](checksum, 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        offset = int.from_bytes(decode[7](data[4:7]), "big")
        size = int.from_bytes(decode[7](data[7:10]), "big")
        form = EncodingFormat(data[10])

        calculated_checksum = sum(data[11:-1]) & 0b1111111
        encoded_checksum = data[-1]
        if calculated_checksum != encoded_checksum:
            raise ValueError(
                f"Calculated checksum (0x{calculated_checksum:02X}) does not"
                f" match encoded checksum (0x{encoded_checksum:02X})!"
            )

        if form == EncodingFormat.Nibblized:
            # Decode in "nibblized" format.
            data_bytes = decode[4](data[11:-1])[-size:]
        else:
            # Decode in "bitstream" (7-bit) format.
            data_bytes = decode[7](data[11:-1])[-size:]

        return cls(_type, idno, offset, form, data_bytes)


Dump._response_classes = [Load]


@define
class DataAcknowledged(SysexMessage):
    """
    Returned when a load command was accepted.
    """

    _msg_type_int = 0x02

    type: ObjectType
    idno: int
    offset: int
    size: int

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.offset, 3)
            + encode[7](self.size, 3)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        offset = int.from_bytes(decode[7](data[4:7]), "big")
        size = int.from_bytes(decode[7](data[7:10]), "big")
        return cls(_type, idno, offset, size)


@define
class DataNotAcknowledged(SysexMessage):
    """
    Returned when a load command was rejected.
    """

    _msg_type_int = 0x03

    class ErrorCode(Enum):
        ObjectCurrentlyBeingEdited = 1
        IncorrectChecksum = 2
        IDOutOfRange = 3
        ObjectNotFound = 4
        RAMIsFull = 5

    type: ObjectType
    idno: int
    offset: int
    size: int
    code: ErrorCode

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.offset, 3)
            + encode[7](self.size, 3)
            + encode[7](self.code.value, 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        offset = int.from_bytes(decode[7](data[4:7]), "big")
        size = int.from_bytes(decode[7](data[7:10]), "big")
        code = cls.ErrorCode(data[10])
        return cls(_type, idno, offset, size, code)


Load._response_classes = [DataAcknowledged, DataNotAcknowledged]


@define
class Dir(SysexMessage):
    """
    Look up a single object's metadata. Response will be an INFO message.
    """

    _msg_type_int = 0x04

    type: ObjectType
    idno: int

    def _encode_body(self):
        return encode[7](self.type.value, 2) + encode[7](self.idno, 2)

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        return cls(_type, idno)


@define
class Info(SysexMessage):
    """
    Response to a Dir, New, or Delete command, containing "info" (metadata)
    about a given object.
    """

    _msg_type_int = 0x05

    type: ObjectType
    idno: int
    size: int
    in_ram: bool
    name: str

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.size, 3)
            + encode[7](int(self.in_ram), 1)
            + self.name.encode("ascii")
            + b"\x00"
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        size = int.from_bytes(decode[7](data[4:7]), "big")
        in_ram = bool(data[7])
        name = bytes(data[8:-1]).decode("ascii")
        return cls(_type, idno, size, in_ram, name)


Dir._response_classes = [Info]


@define
class New(SysexMessage):
    """
    Creates a new object and responds with an INFO message of the created object.
    The object's data will not be initialized to any default values. If 'idno'
    is zero, the first available object ID number will be assigned. If 'create_ram_copy'
    is 0, the request will fail if the object exists. If 'create_ram_copy' is 1, and the
    object exists in ROM, a RAM copy will be made. If 'create_ram_copy' is 1, and the
    object exists in RAM, no action is taken.
    """

    _msg_type_int = 0x06
    _response_classes = [Info]

    type: ObjectType
    idno: int
    size: int
    create_ram_copy: bool
    name: str

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.size, 3)
            + encode[7](int(self.create_ram_copy), 1)
            + self.name.encode("ascii")
            + b"\x00"
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        size = int.from_bytes(decode[7](data[4:7]), "big")
        create_ram_copy = bool(data[7])
        name = bytes(data[8:-1]).decode("ascii")
        return cls(_type, idno, size, create_ram_copy, name)


@define
class Del(SysexMessage):
    """
    Deletes an existing object and responds with an INFO message for
    the deleted object. If there is only a RAM copy of the object,
    the response will indicate that the object doesn't exist anymore.
    However, if the deletion of a RAM object uncovers a ROM object,
    the INFO response will refer to the ROM object. A ROM object
    cannot be deleted.
    """

    _msg_type_int = 0x07
    _response_classes = [Info]

    type: ObjectType
    idno: int

    def _encode_body(self):
        return encode[7](self.type.value, 2) + encode[7](self.idno, 2)

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        return cls(_type, idno)


@define
class Change(SysexMessage):
    """
    Changes the name and/or ID number of an existing object.

    If 'newid' is zero or 'newid' equals 'idno', the ID number
    is not changed. If 'newid' is a legal object id number for
    the object's type, then the existing object will be
    relocated in the database at the new ID number. This will
    cause the deletion of any object which was previously
    assigned to the 'newid'. If the 'name' field is null,
    the name will not change. Otherwise, the name is changed
    to the (null-terminated) string in the 'name' field.
    """

    _msg_type_int = 0x08
    _response_classes = [Info]

    type: ObjectType
    idno: int
    newid: int
    name: str

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](self.newid, 2)
            + self.name.encode("ascii")
            + b"\x00"
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        newid = int.from_bytes(decode[7](data[4:6]), "big")
        name = bytes(data[6:-1]).decode("ascii")
        return cls(_type, idno, newid, name)


@define
class Write(SysexMessage):
    """
    Writes an entire object's data directly into the database.

    It functions like the message sequence DEL followed by NEW
    followed by a LOAD of one complete object data structure.
    It first deletes any object already existing at the same
    type/ID. If no RAM object currently exists there, a new
    one will be allocated and the data will be written into it.

    The object name will be set if the 'name' string is non-null.
    The response to this message will either be a DACK or a DNAK,
    as with the load message. The 'offs' field of the response
    will be zero. The K2500 will send a WRITE message whenever
    an object is dumped from the front-panel (using a 'Dump'
    soft-button), or in response to a READ message.
    """

    _msg_type_int = 0x09
    _response_classes = [DataAcknowledged, DataNotAcknowledged]

    type: ObjectType
    idno: int
    mode: WriteMode
    name: str
    form: EncodingFormat
    data: bytes

    def _encode_body(self):
        if self.form == EncodingFormat.Nibblized:
            encoded_data = encode[4](self.data, int(math.ceil(len(self.data) * 8 / 4)))
        else:
            encoded_data = encode[7](self.data, int(math.ceil(len(self.data) * 8 / 7)))

        checksum = sum(encoded_data, 0) & 0b1111111
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.idno, 2)
            + encode[7](len(self.data), 3)
            + encode[7](self.mode.value, 1)
            + self.name.encode("ascii")
            + b"\x00"
            + encode[7](self.form.value, 1)
            + encoded_data
            + encode[7](checksum, 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        size = int.from_bytes(decode[7](data[4:7]), "big")
        mode = WriteMode(data[7])
        end_of_name = 8 + data[8:].index(b"\x00")
        name = data[8:end_of_name].decode("ascii")
        form = EncodingFormat(data[end_of_name + 1])

        calculated_checksum = sum(data[end_of_name + 2 : -1]) & 0b1111111
        encoded_checksum = data[-1]
        if calculated_checksum != encoded_checksum:
            raise ValueError(
                f"Calculated checksum (0x{calculated_checksum:02X}) does not"
                f" match encoded checksum (0x{encoded_checksum:02X})!"
            )

        if form == EncodingFormat.Nibblized:
            data_bytes = decode[4](data[end_of_name + 2 : -1])[-size:]
        else:
            data_bytes = decode[7](data[end_of_name + 2 : -1])[-size:]

        return cls(_type, idno, mode, name, form, data_bytes)


@define
class Read(SysexMessage):
    """
    Requests the K2 to send a WRITE message for the given object.
    No response will be sent if the object does not exist.
    """

    _msg_type_int = 0x0A
    _response_classes = [Write]

    type: ObjectType
    idno: int
    form: EncodingFormat

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2) + encode[7](self.idno, 2) + encode[7](self.form.value, 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        idno = int.from_bytes(decode[7](data[2:4]), "big")
        form = EncodingFormat(data[4])

        return cls(_type, idno, form)


@define
class ReadBank(SysexMessage):
    """
    Requests the K25 to send a WRITE message for multiple objects within one or all banks.

    'type' and 'bank' specify the group of objects to be returned in WRITE messages.
    The 'type' field specifies a single object type, unless it is zero, in which case
    objects of all user types will be returned (see object type table below). The 'bank'
    field specifies a single bank, 0-9, unless it is set to 127, in which case objects
    from all banks will be returned.
    """

    _msg_type_int = 0x0B
    _response_classes = [Write]

    type: ObjectType
    bank: int
    form: EncodingFormat
    ram_only: bool

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.bank, 1)
            + encode[7](self.form.value, 1)
            + encode[7](int(self.ram_only), 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        bank = data[2]
        form = EncodingFormat(data[3])
        ram_only = bool(data[4])
        return cls(_type, bank, form, ram_only)


@define
class DirBank(SysexMessage):
    """
    This is similar to the READBANK message. The DIRBANK message requests
    an INFO message (containing object size, name, and memory information)
    be returned for each object meeting the specifications in the 'type'
    and 'bank' fields. Following the last INFO response will be an
    ENDOFBANK message.
    """

    _msg_type_int = 0x0C
    _response_classes = [Info]

    type: ObjectType
    bank: int
    ram_only: bool

    def _encode_body(self):
        return (
            encode[7](self.type.value, 2)
            + encode[7](self.bank, 1)
            + encode[7](int(self.ram_only), 1)
        )

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        bank = data[2]
        ram_only = bool(data[3])
        return cls(_type, bank, ram_only)


@define
class EndOfBank(SysexMessage):
    """
    This message is returned after the last WRITE or INFO response
    to a READBANK or DIRBANK message. If no objects matched the
    specifications in one of these messages, ENDOFBANK will be the
    only response.
    """

    _msg_type_int = 0x0D
    _response_classes = [Info]

    type: ObjectType
    bank: int

    def _encode_body(self):
        return encode[7](self.type.value, 2) + encode[7](self.bank, 1)

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        bank = data[2]
        return cls(_type, bank)


@define
class DelBank(SysexMessage):
    """
    This message will cause banks of objects (of one or all types) to
    be deleted from RAM. The 'type' and 'bank' specifications are the
    same as for the READBANK message. The deletion will take place with
    no confirmation. Specifically, the sender of this message could just
    as easily delete every RAM object from the K2500 (e.g. 'type' = 0
    and 'bank' = 127) as it could delete all effects from bank 7 (e.g.
    'type' = 113, 'bank' = 7.)
    """

    _msg_type_int = 0x0E
    _response_classes = [Info]

    type: ObjectType
    bank: int

    def _encode_body(self):
        return encode[7](self.type.value, 2) + encode[7](self.bank, 1)

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        bank = data[2]
        return cls(_type, bank)


@define
class MoveBank(SysexMessage):
    """
    This message is used to move entire banks of RAM objects from one
    bank to another. A specific object type may be selected with the
    'type' field. Otherwise, if the 'type' field is unspecified (0),
    all object types in the bank will be moved. The 'bank' and 'newbank'
    fields must be between 0 and 9. The acknowledgement is an ENDOFBANK
    message, with the 'bank' field equal to the new bank number. If the
    operation can't be completed because of a bad type or bank number,
    the ENDOFBANK message will specify the old bank number.
    """

    _msg_type_int = 0x0F
    _response_classes = [Info]

    type: ObjectType
    bank: int
    newbank: int

    def _encode_body(self):
        return encode[7](self.type.value, 2) + encode[7](self.bank, 1) + encode[7](self.newbank, 1)

    @classmethod
    def _decode_body(cls, data):
        _type = ObjectType(int.from_bytes(decode[7](data[:2]), "big"))
        bank = data[2]
        newbank = data[3]
        return cls(_type, bank, newbank)


@define
class LoadMacro(SysexMessage, EmptyBody):
    """
    tells K2500 to load in the macro currently in memory.
    """

    _msg_type_int = 0x10


@define
class MacroDone(SysexMessage, EmptyBody):
    """
    Acknowledges loading of macro. Code 0 indicates success; code 1 means failure.
    """

    _msg_type_int = 0x11
    error: bool

    def _encode_body(self):
        return encode[7](int(self.error), 1)

    @classmethod
    def _decode_body(cls, data):
        error = bool(data[0])
        return cls(error)


@define
class ButtonEvent:
    """
    A single button action (down, up, repeat, or alpha wheel) for a given button.

    The K2500 Reference Manual suggests:
        For efficiency, multiple button presses should be handled
        by sending multiple Button down bytes followed by a single
        Button up byte (for incrementing with the '+' button, for
        instance.)
    """

    EXPECTED_SIZE = 3

    def __validate_alpha_wheel_clicks(self, attribute, value):
        if value < -64 or value > 63:
            raise ValueError(f"alpha_wheel_clicks must be between -64 and 63, but got {value}")

    event_type: ButtonEventType
    button: Button
    alpha_wheel_clicks: int = field(default=0, validator=__validate_alpha_wheel_clicks)

    @classmethod
    def press(cls, button: Button) -> List["ButtonEvent"]:
        """
        Returns a button down event for the provided button, followed by a button up.
        """
        return [ButtonEvent(ButtonEventType.Down, button), ButtonEvent(ButtonEventType.Up, button)]

    @classmethod
    def decode(cls, data: bytes) -> "ButtonEvent":
        if len(data) != cls.EXPECTED_SIZE:
            raise ValueError(
                f"Expected {cls.EXPECTED_SIZE:,} bytes for ButtonEvent, but got {len(data):,}."
            )

        event_type_int, button_int, alpha_wheel_clicks = data
        return cls(ButtonEventType(event_type_int), Button(button_int), alpha_wheel_clicks - 64)

    def encode(self):
        return bytes([self.event_type.value, self.button.value, self.alpha_wheel_clicks + 64])


@define
class Panel(SysexMessage):
    """
    Execute a button press, as if a button on the K2xxx's front panel was pushed.
    (Internally, the K2's front panel is actually controlled via MIDI between two
    processors, so this is functionally equivalent - although the OS can distinguish
    between button presses coming from internal MIDI and external MIDI.)

    From the reference manual:
        ...sends a sequence of front-panel button presses that are interpreted by
        the K2500 as if the buttons were pressed at its front-panel. The button
        codes are listed in a table at the end of this chapter. The K2500 will
        send these messages if the Buttons parameter on the XMIT page in MIDI
        mode is set to On. Each button press is 3 bytes in the message. The
        PANEL message can include as many 3-byte segments as necessary.
    """

    _msg_type_int = 0x14

    button_events: List[ButtonEvent]

    @classmethod
    def _decode_body(cls, data: bytes) -> "Panel":
        return Panel(
            [ButtonEvent.decode(bytes(chunk)) for chunk in grouper(data, ButtonEvent.EXPECTED_SIZE)]
        )

    def _encode_body(self) -> bytes:
        return b"".join([event.encode() for event in self.button_events])


@define
class AllText(SysexMessage, EmptyBody):
    """
    Request all text in the K2's display.
    """

    _msg_type_int = 0x15


@define
class ParameterValue(SysexMessage, EmptyBody):
    """
    Request the current[ly-selected] parameter value.
    """

    _msg_type_int = 0x16


@define
class ParameterName(SysexMessage, EmptyBody):
    """
    Request the current[ly-selected] parameter name.
    """

    _msg_type_int = 0x17


@define
class GetGraphics(SysexMessage, EmptyBody):
    """
    Request the graphics layer of the K2's display.
    """

    _msg_type_int = 0x18


@define
class ScreenReply(SysexMessage):
    _msg_type_int = 0x19
    _screen_dims = (240, 64)
    _character_dims = (6, 8)

    data: bytes

    def __str__(self):
        if len(self.data) == 321:
            parts = []
            width_in_chars = self._screen_dims[0] // self._character_dims[0]
            for line in grouper(self.data[:-1], width_in_chars):
                chars = [chr(x) for x in line if x]
                parts.append("".join(chars))
            return "\n".join(parts)
        elif len(self.data) == 2561:
            raise TypeError("ScreenReply contains image data and cannot be converted to `str`.")
        else:
            # Probably a variable-length null-terminated ASCII string:
            return self.data.rstrip(b"\x00").decode("ascii")

    def to_pixel_array(self) -> Optional[np.ndarray]:
        if len(self.data) != 2561:
            raise TypeError(
                f"ScreenReply contains string data (of length {len(self.data):,} bytes) and cannot be converted to image."
            )

        pixels = []
        for sixpixels in self.data[:-1]:
            pixels.append(bool(sixpixels & 0b000001))
            pixels.append(bool(sixpixels & 0b000010))
            pixels.append(bool(sixpixels & 0b000100))
            pixels.append(bool(sixpixels & 0b001000))
            pixels.append(bool(sixpixels & 0b010000))
            pixels.append(bool(sixpixels & 0b100000))

        # TODO: Find a way to do this just with NumPy instead of with `grouper` here!
        return np.array(list(grouper(pixels, self._screen_dims[0]))).astype(np.uint8).T * 0xFF

    def _encode_body(self) -> bytes:
        return self.data

    @classmethod
    def _decode_body(cls, data: bytes):
        return cls(data)

    @classmethod
    def from_text(cls, string: str):
        return cls(string.encode("ascii") + b"\x00")

    @classmethod
    def from_screen_contents(cls, string: str):
        return cls(string.ljust(320).encode("ascii") + b"\x00")

    @classmethod
    def from_pixel_array(cls, pixels: np.ndarray):
        if pixels.shape != cls._screen_dims:
            raise ValueError(
                f"Provided pixel data must be of shape {cls._screen_dims}, but got {pixels.shape}."
            )

        encoded_data = []
        # Pack the pixels in 6 bits at a time:
        for group in grouper(pixels.flatten(), 6):
            # Convert each element to a single bit:
            # TODO: Must be a more efficient way to do this.
            binary_string = "".join(["1" if pixel else "0" for pixel in reversed(group)])
            encoded_data.append(bytes([int(binary_string, 2)]))
        return cls(b"".join(encoded_data) + b"\x00")


# Don't just get all subclasses naïvely: Attrs does some magic that means
# the result of __subclasses__ will return the objects before Attrs has
# done the requisite magic on them.
__ALL_MESSAGE_TYPES: List[Type[SysexMessage]] = [
    globals()[subclass.__name__] for subclass in SysexMessage.__subclasses__()
]
for cls in __ALL_MESSAGE_TYPES:
    if cls._msg_type_int is not None:
        _TYPE_MAP[cls._msg_type_int] = cls
