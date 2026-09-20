"""Fixtures for the Home Assistant integration tests.

These run only when Home Assistant and pytest-homeassistant-custom-component
are installed. They drive the real config-entry setup, coordinator and sensor
platform against a faked Modbus transport, so only the wire is mocked -- the
register map, batching and decoding are all exercised for real.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.carlo_gavazzi_em300.api.exception import ModbusException
from custom_components.carlo_gavazzi_em300.api.register_map import (
    EM300_REGISTERS,
    REG_CG_IDENTIFICATION,
    REG_SERIAL_NUMBER,
)
from custom_components.carlo_gavazzi_em300.const import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_PARITY,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TRANSPORT,
    DOMAIN,
    Transport,
)

TEST_SERIAL = "A1B2C34"
TEST_PORT = "/dev/ttyUSB0"

#: An EM340 with a 230 V / 5 A / 1150 W single-phase load on L1.
MEASUREMENTS = {
    "v_l1_n": 2301,
    "v_ln_sys": 2301,
    "a_l1": 5000,
    "w_l1": 11500,
    "w_sys": 11500,
    "pf_sys": 1000,
    "hz": 500,
    "kwh_pos_tot": 12345,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the custom integration in every test."""
    yield


def build_words(identification_code: int = 341) -> dict[int, int]:
    """Build the word map of a meter answering with :data:`MEASUREMENTS`."""
    words = {
        address: 0 for register in EM300_REGISTERS for address in register.addresses
    }

    by_name = {register.name: register for register in EM300_REGISTERS}
    for name, value in MEASUREMENTS.items():
        register = by_name[name]
        unsigned = value & ((1 << (16 * register.length)) - 1)
        for offset, address in enumerate(register.addresses):
            # LSW first, per protocol section 2.1.
            words[address] = (unsigned >> (16 * offset)) & 0xFFFF

    words[REG_CG_IDENTIFICATION.address] = identification_code
    for offset, char in enumerate(TEST_SERIAL):
        words[REG_SERIAL_NUMBER.address + offset] = ord(char)
    words[0x0302], words[0x0303] = 0, 3  # firmware A3
    return words


class FakeTransport:
    """A stand-in for :class:`Em300Client` backed by an in-memory word map."""

    def __init__(self, words=None, unit=1):
        self.words = build_words() if words is None else words
        self.unit = unit
        self.connected_count = 0
        self.closed = False
        self.fail = False

    async def connect(self):
        if self.fail:
            raise ModbusException("connection refused")
        self.connected_count += 1

    def close(self):
        self.closed = True

    async def read_holding_registers(self, start, length):
        if self.fail:
            raise ModbusException("link down")
        addresses = range(start, start + length)
        if any(address not in self.words for address in addresses):
            raise ModbusException(f"illegal data address at 0x{start:04X}")
        return {address: self.words[address] for address in addresses}

    async def read_holding_register(self, address):
        return (await self.read_holding_registers(address, 1))[address]

    async def read_batch(self, reads):
        values = {}
        for start, length in reads:
            values.update(await self.read_holding_registers(start, length))
        return values


@pytest.fixture
def transport():
    """The fake Modbus transport every client in the test is built from."""
    return FakeTransport()


@contextmanager
def patch_client(**kwargs):
    """Patch client construction everywhere the integration does it.

    Both call sites must be patched together: the config flow probes the meter
    itself, and creating an entry makes Home Assistant set that entry up
    straight away, which builds a second client.
    """
    targets = (
        "custom_components.carlo_gavazzi_em300.client_from_config",
        "custom_components.carlo_gavazzi_em300.config_flow.client_from_config",
    )
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, **kwargs))
        yield


@pytest.fixture
def mock_client(transport):
    """Patch client construction to hand out the fake transport."""
    with patch_client(return_value=transport):
        yield transport


def serial_config(**overrides):
    """Config entry data for a serial connection."""
    return {
        CONF_TRANSPORT: Transport.SERIAL,
        CONF_SERIAL_PORT: TEST_PORT,
        CONF_BAUDRATE: 9600,
        CONF_PARITY: "none",
        CONF_STOPBITS: 1,
        CONF_BYTESIZE: 8,
        CONF_ADDRESS: 1,
        CONF_SCAN_INTERVAL: 30,
        **overrides,
    }


@pytest.fixture
def config_entry(hass):
    """A configured EM340 entry, not yet set up."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="EM340 A1B2C34",
        unique_id=TEST_SERIAL,
        data={
            **serial_config(),
            "name": "EM340 A1B2C34",
            "model": "EM340",
            "serial_number": TEST_SERIAL,
            "firmware": "A3",
        },
    )
    entry.add_to_hass(hass)
    return entry
