"""Build a Modbus client from stored config entry data.

Shared by the config flow (which connects to validate what the user typed) and
by setup (which connects for real), so both always interpret the entry the
same way.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_ADDRESS, CONF_HOST, CONF_PORT

from .api.client import (
    DEFAULT_PARITY as DEFAULT_PARITY_CHARACTER,
)
from .api.client import (
    Em300Client,
    Em300SerialClient,
    Em300TcpClient,
)
from .const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_FRAMER,
    CONF_PARITY,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TRANSPORT,
    DEFAULT_ADDRESS,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_FRAMER,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DEFAULT_TCP_PORT,
    PARITY_CHARACTERS,
    Transport,
)


def client_from_config(data: dict[str, Any]) -> Em300Client:
    """Build the client described by a config entry's data.

    :raises ModbusPortException: if a serial port cannot exist on this host.
    """
    unit = data.get(CONF_ADDRESS, DEFAULT_ADDRESS)

    if data.get(CONF_TRANSPORT, Transport.SERIAL) == Transport.TCP:
        return Em300TcpClient(
            host=data[CONF_HOST],
            port=data.get(CONF_PORT, DEFAULT_TCP_PORT),
            framer=data.get(CONF_FRAMER, DEFAULT_FRAMER),
            unit=unit,
        )

    return Em300SerialClient(
        port=data[CONF_SERIAL_PORT],
        baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        stopbits=data.get(CONF_STOPBITS, DEFAULT_STOPBITS),
        parity=PARITY_CHARACTERS.get(
            data.get(CONF_PARITY, DEFAULT_PARITY), DEFAULT_PARITY_CHARACTER
        ),
        bytesize=data.get(CONF_BYTESIZE, DEFAULT_BYTESIZE),
        unit=unit,
    )
