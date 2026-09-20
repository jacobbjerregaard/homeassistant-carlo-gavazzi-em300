"""Decoding utilities for the Carlo Gavazzi EM/ET300 register map.

Section 2.1 of the communication protocol fixes two orderings: inside a single
word the byte order is MSB -> LSB (pymodbus already hands us those words as
integers), and across the words of an ``INT32``/``UINT32``/``INT64`` value the
word order is **LSW -> MSW**. This module reassembles that wire ordering into
the logical value, applies the register's "value weight" and builds the
``{name: value}`` mapping the platforms consume.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from .models import Em300Register, RegisterDataType

_LOGGER = logging.getLogger(__name__)

__all__ = ("decode_register", "decode_registers", "to_signed")

#: Data types assembled from several words, LSW first.
_MULTI_WORD = (
    RegisterDataType.INT32,
    RegisterDataType.UINT32,
    RegisterDataType.INT64,
)

#: Data types whose assembled value is two's complement.
_SIGNED = (RegisterDataType.INT16, RegisterDataType.INT32, RegisterDataType.INT64)


def to_signed(value: int, bits: int) -> int:
    """Reinterpret an unsigned ``bits``-wide value as two's complement."""
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


def _decode_string(words: list[int]) -> str:
    """Assemble an ASCII string from one character per word.

    The protocol puts the character in each word's LSB and marks the MSB "not
    to be used". Anything outside printable ASCII is dropped rather than
    carried through: meters pad the block with NULs, and one that does not know
    its own serial number answers with an all-zero block. ``str.strip()`` does
    not remove NULs, so leaving them in would produce a string that still looks
    non-empty to every caller -- and end up in a unique id, an entry title and
    the entity ids slugified from it.
    """
    return "".join(
        character for word in words if " " <= (character := chr(word & 0xFF)) <= "~"
    ).strip()


def decode_register(
    register: Em300Register,
    register_values: Mapping[int, int],
) -> Any | None:
    """Decode one register out of a ``{address: raw_word}`` mapping.

    Returns ``None`` when any word the register spans is absent, so a short
    read drops only the affected register instead of the whole batch.
    """
    words: list[int] = []
    for address in register.addresses:
        word = register_values.get(address)
        if word is None:
            _LOGGER.debug("missing word 0x%04X for register %s", address, register.name)
            return None
        words.append(word)

    if register.data_type is RegisterDataType.STRING:
        return _decode_string(words)

    if register.data_type in _MULTI_WORD:
        # Words arrive least-significant first, so fold them in reverse.
        value = 0
        for word in reversed(words):
            value = (value << 16) | word
    else:
        value = words[0]

    if register.data_type in _SIGNED:
        value = to_signed(value, 16 * len(words))

    if register.scale:
        return round(value / register.scale, 6)
    return value


def decode_registers(
    registers: Iterable[Em300Register],
    register_values: Mapping[int, int],
) -> dict[str, Any]:
    """Decode a ``{address: raw_word}`` Modbus response into ``{name: value}``.

    Registers whose words are missing from the response are skipped rather than
    reported as ``None``, leaving the previous value in place on the entity.
    """
    result: dict[str, Any] = {}

    for register in registers:
        value = decode_register(register, register_values)
        if value is not None:
            result[register.name] = value

    return result
