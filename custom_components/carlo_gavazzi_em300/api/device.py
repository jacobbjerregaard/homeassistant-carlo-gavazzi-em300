"""High-level EM/ET300 device abstraction.

Sits between the raw :mod:`.client` transport and the Home Assistant
coordinator: identifies the meter once at setup, narrows the register map to
what that model actually reports, and turns each poll into a decoded
``{name: value}`` mapping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .batch import RegisterBatch
from .client import Em300Client
from .exception import Em300Exception
from .models import Em300Register, Series
from .register_map import (
    CG_CODE_REVERSED_WORD_ORDER,
    EM300_IDENTITY_REGISTERS,
    EM300_REGISTERS,
    REG_CG_IDENTIFICATION,
    REG_SERIAL_NUMBER,
    series_for_identification_code,
)
from .utils import decode_register, decode_registers

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Em300DeviceInfo:
    """What a meter reports about itself at setup time."""

    serial_number: str | None
    series: Series | None
    identification_code: int | None
    firmware: str | None

    @property
    def model(self) -> str:
        """A display name for the device registry."""
        if self.series is not None:
            return self.series.value
        if self.identification_code is not None:
            return f"EM/ET300 (code {self.identification_code})"
        return "EM/ET300"


class Em300Device:
    """A single EM/ET300 meter reached through one transport."""

    def __init__(self, client: Em300Client) -> None:
        """Start with the full register map; :meth:`identify` narrows it."""
        self.client = client
        self.info: Em300DeviceInfo | None = None
        self.registers: tuple[Em300Register, ...] = EM300_REGISTERS
        self.batch = RegisterBatch(self.registers)

    async def connect(self) -> None:
        """Open the underlying transport."""
        await self.client.connect()

    def close(self) -> None:
        """Close the underlying transport."""
        self.client.close()

    @property
    def unit(self) -> int:
        """The Modbus unit id the meter answers on."""
        return self.client.unit

    async def identify(self, fallback_series: Series | None = None) -> Em300DeviceInfo:
        """Read the meter's identity and narrow the polled register set.

        Each read is attempted independently and tolerated on failure: an
        older meter may not implement the serial-number block, and that should
        degrade the device registry entry rather than block setup.

        ``fallback_series`` is the series a previous setup identified. Without
        it a transient failure on the identification read would widen the
        register set back to everything, create entities for registers this
        model does not have, and orphan them again on the next restart.
        """
        identification_code = await self._read_identification_code()
        series = series_for_identification_code(identification_code)
        if series is None:
            series = fallback_series

        if identification_code == CG_CODE_REVERSED_WORD_ORDER:
            _LOGGER.warning(
                "Meter reports identification code %s, a pre-production EM340 "
                "engineering sample that stores 32-bit values MSW-first "
                "instead of LSW-first. Multi-word readings will be wrong",
                identification_code,
            )

        info = Em300DeviceInfo(
            serial_number=await self._read_serial_number(),
            series=series,
            identification_code=identification_code,
            firmware=await self._read_firmware(),
        )

        self.info = info
        self.registers = tuple(
            register for register in EM300_REGISTERS if register.supported_by(series)
        )
        self.batch = RegisterBatch(self.registers)

        _LOGGER.debug(
            "Identified %s (serial %s, firmware %s): polling %d of %d registers",
            info.model,
            info.serial_number,
            info.firmware,
            len(self.registers),
            len(EM300_REGISTERS),
        )
        return info

    async def _read_identification_code(self) -> int | None:
        """Read the Carlo Gavazzi identification code (table 2.8-1)."""
        try:
            return await self.client.read_holding_register(
                REG_CG_IDENTIFICATION.address
            )
        except (Em300Exception, OSError, TimeoutError):
            _LOGGER.debug("Could not read identification code", exc_info=True)
            return None

    async def _read_serial_number(self) -> str | None:
        """Read the seven-word ASCII serial number (table 2.9-9)."""
        try:
            words = await self.client.read_holding_registers(
                REG_SERIAL_NUMBER.address, REG_SERIAL_NUMBER.length or 7
            )
        except (Em300Exception, OSError, TimeoutError):
            _LOGGER.debug("Could not read serial number", exc_info=True)
            return None

        serial = decode_register(REG_SERIAL_NUMBER, words)
        return serial or None

    async def _read_firmware(self) -> str | None:
        """Read the version and revision codes (table 2.7-1).

        Version 0 means "A", 1 means "B" and so on; revision 0 means "0". The
        two are combined into a single ``A0``-style string.
        """
        try:
            values = await self.client.read_batch(
                RegisterBatch(EM300_IDENTITY_REGISTERS).reads
            )
        except (Em300Exception, OSError, TimeoutError):
            _LOGGER.debug("Could not read firmware version", exc_info=True)
            return None

        decoded = decode_registers(EM300_IDENTITY_REGISTERS, values)
        version = decoded.get("version_code")
        revision = decoded.get("revision_code")
        if version is None or revision is None:
            return None
        return f"{chr(ord('A') + version)}{revision}"

    async def read_all(self) -> dict[str, Any]:
        """Poll every supported register and return decoded values by name."""
        values = await self.client.read_batch(self.batch.reads)
        return decode_registers(self.batch.registers, values)
