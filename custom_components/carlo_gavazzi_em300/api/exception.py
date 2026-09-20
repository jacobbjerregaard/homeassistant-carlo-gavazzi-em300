"""Custom exceptions for the Carlo Gavazzi EM300 integration."""

from __future__ import annotations


class Em300Exception(Exception):
    """Base exception for the EM300 integration."""


class ModbusException(Em300Exception):
    """Raised when a Modbus transaction is rejected by the device.

    pymodbus surfaces a rejected read/write as an exception *response* rather
    than a Python exception, so the client layer converts those here.
    """


class ModbusPortException(Em300Exception):
    """Raised when a serial/UDP port cannot be opened."""
