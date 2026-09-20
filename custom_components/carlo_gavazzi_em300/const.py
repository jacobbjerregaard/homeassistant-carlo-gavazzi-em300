"""Constants for the Carlo Gavazzi EM300 Modbus integration."""

from __future__ import annotations

from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "carlo_gavazzi_em300"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]

# --- Configuration keys -----------------------------------------------------
# Keys that exist in ``homeassistant.const`` (CONF_HOST, CONF_PORT, CONF_NAME,
# CONF_ADDRESS, CONF_SCAN_INTERVAL) are imported from there at the point of
# use; only the ones specific to this integration are defined here.
CONF_TRANSPORT = "transport"
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_STOPBITS = "stopbits"
CONF_PARITY = "parity"
CONF_BYTESIZE = "bytesize"
CONF_FRAMER = "framer"

CONF_SERIAL_NUMBER = "serial_number"
CONF_MODEL = "model"
CONF_FIRMWARE = "firmware"

# The meter series identified at setup, remembered so a failed identification
# read does not change which entities exist.
CONF_SERIES = "series"


class Transport(StrEnum):
    """How the integration reaches the meter."""

    SERIAL = "serial"
    TCP = "tcp"


class ParityOption(StrEnum):
    """Serial parity settings, as the single character pymodbus expects."""

    NONE = "N"
    EVEN = "E"
    ODD = "O"


class FramerOption(StrEnum):
    """Modbus framing used over TCP.

    A native Modbus TCP gateway speaks ``socket``; a transparent RS485-to-
    Ethernet bridge usually tunnels raw ``rtu`` frames instead.
    """

    SOCKET = "socket"
    RTU = "rtu"


# --- Defaults ---------------------------------------------------------------
DEFAULT_NAME = "Carlo Gavazzi EM300"

# The meter's factory serial settings (see its own serial port configuration
# menu); these must match how the meter itself is programmed.
DEFAULT_BAUDRATE = 9600
DEFAULT_STOPBITS = 1
DEFAULT_PARITY = ParityOption.NONE
DEFAULT_BYTESIZE = 8

DEFAULT_TCP_PORT = 502
DEFAULT_FRAMER = FramerOption.SOCKET

DEFAULT_ADDRESS = 1
DEFAULT_SCAN_INTERVAL = 30

# Valid RS485 addresses (protocol section 1.2: 1 to F7h).
MIN_ADDRESS = 1
MAX_ADDRESS = 247

# The meter updates its measurements roughly once a second; polling faster
# than this only adds bus traffic.
MIN_SCAN_INTERVAL = 1
MAX_SCAN_INTERVAL = 600

BAUDRATE_OPTIONS = [9600, 19200, 38400, 57600, 115200]
STOPBITS_OPTIONS = [1, 2]
BYTESIZE_OPTIONS = [7, 8]
