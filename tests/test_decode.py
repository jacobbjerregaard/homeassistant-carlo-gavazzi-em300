"""Tests for register decoding.

The wire format is fixed by protocol section 2.1: MSB->LSB inside a word,
LSW->MSW across the words of a 32- or 64-bit value.
"""

import pytest
from em300_api.models import Em300Register, RegisterDataType
from em300_api.utils import decode_register, decode_registers, to_signed


def words_lsw_first(value: int, width_bits: int) -> list[int]:
    """Split ``value`` into words the way the meter puts them on the wire."""
    unsigned = value & ((1 << width_bits) - 1)
    return [(unsigned >> shift) & 0xFFFF for shift in range(0, width_bits, 16)]


def raw(register: Em300Register, value: int, width_bits: int) -> dict[int, int]:
    """Build an ``{address: word}`` map holding ``value`` for ``register``."""
    return dict(
        zip(register.addresses, words_lsw_first(value, width_bits), strict=True)
    )


INT32 = Em300Register(name="v", address=0x0100, data_type=RegisterDataType.INT32)
UINT32 = Em300Register(name="v", address=0x0100, data_type=RegisterDataType.UINT32)
INT16 = Em300Register(name="v", address=0x0100, data_type=RegisterDataType.INT16)
UINT16 = Em300Register(name="v", address=0x0100, data_type=RegisterDataType.UINT16)
INT64 = Em300Register(name="v", address=0x0100, data_type=RegisterDataType.INT64)


@pytest.mark.parametrize(
    ("value", "bits"),
    [(0, 16), (1, 16), (32767, 16), (-1, 16), (-32768, 16)],
)
def test_to_signed_round_trips_16_bit_values(value, bits):
    assert to_signed(value & 0xFFFF, bits) == value


def test_int32_is_assembled_least_significant_word_first():
    # 0x0001_0000 == 65536: the high word carries the 1, and it arrives second.
    assert decode_register(INT32, {0x0100: 0x0000, 0x0101: 0x0001}) == 65536


def test_int32_assembled_the_other_way_round_would_be_wrong():
    # Guards against a regression to MSW-first, which would read 65536 here.
    assert decode_register(INT32, {0x0100: 0x0001, 0x0101: 0x0000}) == 1


@pytest.mark.parametrize("value", [0, 1, -1, 2147483647, -2147483648, -1234567])
def test_int32_round_trips_signed_values(value):
    assert decode_register(INT32, raw(INT32, value, 32)) == value


@pytest.mark.parametrize("value", [0, 1, 4294967295, 2147483648])
def test_uint32_never_goes_negative(value):
    assert decode_register(UINT32, raw(UINT32, value, 32)) == value


@pytest.mark.parametrize("value", [0, 1, -1, 32767, -32768])
def test_int16_round_trips_signed_values(value):
    assert decode_register(INT16, raw(INT16, value, 16)) == value


@pytest.mark.parametrize("value", [0, 1, 65535, 32768])
def test_uint16_never_goes_negative(value):
    assert decode_register(UINT16, raw(UINT16, value, 16)) == value


@pytest.mark.parametrize("value", [0, 1, -1, 2**62, -(2**62)])
def test_int64_round_trips_signed_values(value):
    assert decode_register(INT64, raw(INT64, value, 64)) == value


class TestScaling:
    """The "value weight" turns the raw integer into an engineering unit."""

    def test_volt_weight_of_ten(self):
        register = Em300Register(
            name="v", address=0, data_type=RegisterDataType.INT32, scale=10
        )
        assert decode_register(register, raw(register, 2301, 32)) == 230.1

    def test_ampere_weight_of_a_thousand(self):
        register = Em300Register(
            name="a", address=0, data_type=RegisterDataType.INT32, scale=1000
        )
        assert decode_register(register, raw(register, 5432, 32)) == 5.432

    def test_negative_power_keeps_its_sign(self):
        register = Em300Register(
            name="w", address=0, data_type=RegisterDataType.INT32, scale=10
        )
        assert decode_register(register, raw(register, -12345, 32)) == -1234.5

    def test_unscaled_register_is_returned_as_an_integer(self):
        register = Em300Register(
            name="seq", address=0, data_type=RegisterDataType.INT16
        )
        assert decode_register(register, {0: 1}) == 1


class TestStrings:
    """The serial number is one ASCII character per word, in the LSB."""

    register = Em300Register(
        name="serial", address=0x5000, data_type=RegisterDataType.STRING, length=7
    )

    def test_ascii_characters_are_read_from_the_low_byte(self):
        values = {0x5000 + i: ord(c) for i, c in enumerate("A1B2C34")}
        assert decode_register(self.register, values) == "A1B2C34"

    def test_the_high_byte_is_ignored(self):
        # The protocol marks the MSB "not to be used"; a meter that leaves
        # junk there must not corrupt the serial number.
        values = {0x5000 + i: 0xFF00 | ord(c) for i, c in enumerate("A1B2C34")}
        assert decode_register(self.register, values) == "A1B2C34"

    def test_padding_is_stripped(self):
        values = {0x5000 + i: ord(c) for i, c in enumerate("AB     ")}
        assert decode_register(self.register, values) == "AB"

    def test_nul_padding_is_stripped(self):
        # str.strip() does not remove NULs, so a meter that NUL-pads a short
        # serial number used to yield "AB\x00\x00\x00\x00\x00".
        values = {0x5000 + i: v for i, v in enumerate([0x41, 0x42, 0, 0, 0, 0, 0])}
        assert decode_register(self.register, values) == "AB"

    def test_an_all_zero_block_decodes_to_the_empty_string(self):
        # A meter that does not know its own serial number answers with zeros.
        # This has to be falsy, or callers cannot tell it from a real value and
        # every such meter ends up sharing one unique id.
        values = {0x5000 + i: 0 for i in range(7)}
        decoded = decode_register(self.register, values)
        assert decoded == ""
        assert not decoded

    def test_control_characters_are_dropped(self):
        values = {
            0x5000 + i: v for i, v in enumerate([0x41, 0x0A, 0x42, 0x7F, 0, 0, 0])
        }
        assert decode_register(self.register, values) == "AB"


class TestMissingWords:
    """A short read must drop only the registers it actually affects."""

    def test_a_missing_low_word_yields_none(self):
        assert decode_register(INT32, {0x0101: 1}) is None

    def test_a_missing_high_word_yields_none(self):
        # The high word is the one an address-only batch plan used to skip,
        # which silently halved every 32-bit reading.
        assert decode_register(INT32, {0x0100: 1}) is None

    def test_an_empty_response_yields_none(self):
        assert decode_register(INT32, {}) is None

    def test_other_registers_still_decode(self):
        first = Em300Register(
            name="first", address=0x0000, data_type=RegisterDataType.INT32
        )
        second = Em300Register(
            name="second", address=0x0010, data_type=RegisterDataType.INT32
        )
        values = {0x0000: 7, 0x0001: 0, 0x0010: 9}  # second is short a word

        decoded = decode_registers([first, second], values)

        assert decoded == {"first": 7}
