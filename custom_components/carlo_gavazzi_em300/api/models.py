"""Data model for a single Carlo Gavazzi EM300/ET300 register slot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegisterDataType(str, Enum):
    """Supported Modbus register data formats on the EM/ET300 register map.

    Per section 2.1 of the communication protocol, the byte order inside a
    single word is always MSB -> LSB, while ``INT32``/``UINT32``/``INT64``
    values are stored **LSW-first** across their words.

    Note that despite the format table listing IEEE754 single precision, no
    register in the EM/ET300 map actually uses it; every measurement is a
    scaled integer.
    """

    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    INT64 = "int64"
    STRING = "string"


#: How many words each fixed-width data type occupies.
_FIXED_WIDTHS: dict[RegisterDataType, int] = {
    RegisterDataType.INT16: 1,
    RegisterDataType.UINT16: 1,
    RegisterDataType.INT32: 2,
    RegisterDataType.UINT32: 2,
    RegisterDataType.INT64: 4,
}


class Series(str, Enum):
    """Meter families in the EM/ET300 range.

    Some registers exist only on part of the range (the run-hour meter is
    documented as "only ET series and EM330", the negative per-phase energy
    totalizers as "only ET series"). Registers carry the set of series they are
    valid on so the integration does not create entities that can only ever
    report zero.
    """

    EM330 = "EM330"
    EM331 = "EM331"
    EM340 = "EM340"
    EM341 = "EM341"
    ET330 = "ET330"
    ET340 = "ET340"


#: Every series in the range; the default for registers with no restriction.
ALL_SERIES: frozenset[Series] = frozenset(Series)

#: The ET-only subset, used by the negative per-phase energy totalizers.
ET_SERIES: frozenset[Series] = frozenset({Series.ET330, Series.ET340})

#: ET series plus EM330, used by the run-hour meter.
ET_SERIES_AND_EM330: frozenset[Series] = ET_SERIES | {Series.EM330}


@dataclass(frozen=True, kw_only=True)
class Em300Register:
    """A single register slot on an EM/ET300 meter.

    Parameters
    ----------
    name:
        Internal, stable identifier used as the entity's ``key`` and as the
        key the coordinator stores the decoded value under.
    address:
        The Modbus word address as transmitted on the wire -- the protocol's
        "physical address" column, e.g. ``0x0000`` for V L1-N. The "Modicom
        address" column is *not* used; no translation is applied.
    length:
        The value width in words. Implied by ``data_type`` for the fixed-width
        types, and required for ``STRING``.
    data_type:
        How to interpret the raw words (see :class:`RegisterDataType`).
    scale:
        The protocol's "value weight". The decoded integer is divided by this
        to obtain the human readable value, e.g. ``10`` for Volt*10 or ``1000``
        for Ampere*1000. ``None`` for unscaled values such as the phase
        sequence flag or the serial number.
    series:
        The meter series this register carries a real value on.
    standalone:
        ``True`` for registers the protocol requires be read one word at a
        time, which excludes them from batched reads. Only the Carlo Gavazzi
        identification code is documented this way -- its word overlaps the
        most significant word of V L3-L1, so it is only meaningful when read
        on its own.
    """

    name: str
    address: int
    data_type: RegisterDataType
    length: int | None = None
    scale: float | None = None
    series: frozenset[Series] = ALL_SERIES
    standalone: bool = False

    def __post_init__(self) -> None:
        """Derive and validate ``length`` against the register's data type."""
        expected = _FIXED_WIDTHS.get(self.data_type)

        if expected is None:  # STRING: caller must say how long it is.
            if self.length is None or self.length < 1:
                raise ValueError(
                    f"{self.name}: {self.data_type.value} requires an explicit "
                    "length of at least 1 word"
                )
            return

        if self.length is None:
            # ``frozen=True`` blocks plain assignment, so go through object.
            object.__setattr__(self, "length", expected)
        elif self.length != expected:
            raise ValueError(
                f"{self.name}: {self.data_type.value} occupies {expected} "
                f"word(s), got {self.length}"
            )

    @property
    def addresses(self) -> range:
        """Every word address this register spans."""
        assert self.length is not None  # established by __post_init__
        return range(self.address, self.address + self.length)

    def supported_by(self, series: Series | None) -> bool:
        """Whether this register carries a real value on ``series``.

        An unknown series (``None``) is treated as supporting everything, so a
        meter whose identification code we failed to read still gets the full
        entity set rather than none of it.
        """
        return series is None or series in self.series
