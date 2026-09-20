"""Transport layer for the Carlo Gavazzi EM/ET300.

Wraps pymodbus behind a small async client covering the two ways an EM/ET300
is reached: directly over RS485, or through an RS485-to-Ethernet gateway.
Every transaction is serialised through a lock, because Modbus is a single
request/response link on which overlapping transactions corrupt each other's
frames.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Mapping

from pymodbus import FramerType
from pymodbus.client import ModbusBaseClient
from pymodbus.client.serial import AsyncModbusSerialClient
from pymodbus.client.tcp import AsyncModbusTcpClient

from .exception import ModbusException, ModbusPortException

_LOGGER = logging.getLogger(__name__)

#: Default RS485 settings; the meter's own serial menu must match these.
DEFAULT_BAUDRATE = 9600
DEFAULT_PARITY = "N"
DEFAULT_STOPBITS = 1
DEFAULT_BYTESIZE = 8

#: Default TCP port for Modbus gateways.
DEFAULT_TCP_PORT = 502

DEFAULT_TIMEOUT = 5
DEFAULT_RETRIES = 3


class Em300Client:
    """Base transport for a single EM/ET300 meter.

    Subclasses build :attr:`client` for their transport; everything above that
    -- locking, batched reads, error translation -- is shared.

    :ivar unit: The Modbus unit/slave id the meter answers on.
    """

    client: ModbusBaseClient

    def __init__(self, unit: int = 1) -> None:
        """Initialise the shared transaction lock."""
        self.unit = unit
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open the underlying connection."""
        await self.client.connect()

    def connected(self) -> bool:
        """Whether the connection is currently open."""
        return self.client.connected

    def close(self) -> None:
        """Close the underlying connection."""
        self.client.close()

    async def read_holding_registers(
        self, start_index: int, length: int
    ) -> dict[int, int]:
        """Read ``length`` holding registers starting at ``start_index``.

        Function codes 03h and 04h have identical effect on this meter
        (protocol section 1.2, note 2), so only 03h is used.
        """
        async with self._lock:
            data = await self.client.read_holding_registers(
                address=start_index, count=length, device_id=self.unit
            )

        # pymodbus signals a rejected read with an exception *response* rather
        # than by raising, so an unchecked result would look like a success.
        if data is None or data.isError():
            raise ModbusException(
                f"Modbus error reading {length} holding register(s) at "
                f"0x{start_index:04X}: {data}"
            )

        registers = dict(enumerate(data.registers, start_index))
        if len(registers) != length:
            raise ModbusException(
                f"Short Modbus read at 0x{start_index:04X}: asked for "
                f"{length} register(s), got {len(registers)}"
            )
        return registers

    async def read_holding_register(self, address: int) -> int:
        """Read a single holding register.

        Used for the Carlo Gavazzi identification code, which the protocol
        requires be read "a word at a time".
        """
        return (await self.read_holding_registers(address, 1))[address]

    async def read_batch(self, reads: Mapping[int, int] | list[tuple[int, int]]):
        """Execute several ``(start, length)`` reads into one address map."""
        pairs = reads.items() if isinstance(reads, Mapping) else reads
        values: dict[int, int] = {}
        for start, length in pairs:
            values.update(await self.read_holding_registers(start, length))
        return values

    async def write_register(self, address: int, payload: int) -> None:
        """Write a raw 16-bit value to a holding register (function 06h).

        :raises ModbusException: if the meter rejected the write.
        """
        async with self._lock:
            result = await self.client.write_register(
                address, payload & 0xFFFF, device_id=self.unit
            )

        if result is None or result.isError():
            raise ModbusException(f"Modbus error writing 0x{address:04X}: {result}")


class Em300SerialClient(Em300Client):
    """Talks to a meter over a local RS485 serial port."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        stopbits: int = DEFAULT_STOPBITS,
        parity: str = DEFAULT_PARITY,
        bytesize: int = DEFAULT_BYTESIZE,
        unit: int = 1,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Validate the port and build the pymodbus serial client.

        :raises ModbusPortException: if the port cannot exist on this platform.
        """
        super().__init__(unit=unit)
        _validate_serial_port(port)

        self.client = AsyncModbusSerialClient(
            port=port,
            framer=FramerType.RTU,
            baudrate=baudrate,
            stopbits=stopbits,
            parity=parity[:1],
            bytesize=bytesize,
            timeout=timeout,
        )


class Em300TcpClient(Em300Client):
    """Talks to a meter through an RS485-to-Ethernet gateway."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_TCP_PORT,
        framer: str = "socket",
        unit: int = 1,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        """Build the pymodbus TCP client.

        Gateways differ in whether they expect Modbus TCP framing or RTU
        frames tunnelled over TCP, so the framer is configurable.
        """
        super().__init__(unit=unit)

        self.client = AsyncModbusTcpClient(
            host,
            port=port,
            framer=framer_type(framer),
            timeout=timeout,
            retries=retries,
        )


def framer_type(framer: str) -> FramerType:
    """Map a configured framing name to the pymodbus framer.

    A native Modbus TCP gateway speaks ``socket`` framing; a transparent
    RS485-to-Ethernet bridge tunnels raw RTU frames instead. Anything
    unrecognised falls back to Modbus TCP, which is the common case.
    """
    return FramerType.RTU if framer.lower() == "rtu" else FramerType.SOCKET


def _validate_serial_port(port: str) -> None:
    """Reject a serial port that cannot exist on the running platform.

    :raises ModbusPortException: if the port name or path is unusable.
    """
    if sys.platform.startswith("win"):
        if not port.upper().startswith("COM"):
            raise ModbusPortException(
                f"Serial port {port} is not valid on Windows; it should start "
                "with 'COM'"
            )
        return

    if not os.path.exists(port):
        raise ModbusPortException(f"Serial port {port} is not available")
