from enum import Enum


class ObjectType(Enum):
    """
    The type of an object in the K2000.
    """

    Program = 132
    Keymap = 133
    Effect = 113
    Song = 112
    Setup = 135
    Soundblock = 134
    VelocityMap = 104
    PressureMap = 105
    QuickAccessBank = 111
    IntonationTable = 103


class ButtonEventType(Enum):
    Up = 0x08
    Down = 0x09
    Repeat = 0x0A
    AlphaWheel = 0x0D


class Button(Enum):
    Number0 = 0x00
    Number1 = 0x01
    Number2 = 0x02
    Number3 = 0x03
    Number4 = 0x04
    Number5 = 0x05
    Number6 = 0x06
    Number7 = 0x07
    Number8 = 0x08
    Number9 = 0x09
    PlusMinus = 0x0A
    Cancel = 0x0B
    Clear = 0x0C
    Enter = 0x0D
    Plus = 0x16
    Minus = 0x17
    PlusAndMinus = 0x1E
    ChanBankInc = 0x14
    ChanBankDec = 0x15
    ChanBankIncDec = 0x1C
    CursorLeft = 0x12
    CursorRight = 0x13
    CursorLeftRight = 0x1A
    CursorUp = 0x10
    CursorDown = 0x11
    SoftA = 0x22
    SoftB = 0x23
    SoftC = 0x24
    SoftD = 0x25
    SoftE = 0x26
    SoftF = 0x27
    SoftAB = 0x28
    SoftCD = 0x29
    SoftEF = 0x2A
    SoftYes = 0x26
    SoftNo = 0x27
    Edit = 0x20
    Exit = 0x21
    Program = 0x40
    Setup = 0x41
    QuickAccess = 0x42
    Effects = 0x47
    MIDI = 0x44
    Master = 0x43
    Song = 0x46
    Disk = 0x45


class EncodingFormat(Enum):
    """
    Encode each 8-bit byte into two 4-bit, right-aligned bytes.
    """

    Nibblized = 0

    """
    Encode the data bytes as consecutive 7-bit bytes.
    """
    BitStream = 1


class WriteMode(Enum):
    """
    If WriteToExactIDNumber is provided, the Write command's `idno` specifies the exact ID to write to.
    If the `idno` provided is `0`, the first available ID number will be written to.
    """

    WriteToExactIDNumber = 0

    """
    The object is written at the first available ID number after what is specified by 'idno'.
    """
    WriteToFirstAvailableIDAfterSpecified = 1
