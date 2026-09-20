"""Reconfiguring an existing entry's connection settings."""

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.carlo_gavazzi_em300.const import (
    CONF_SERIAL_PORT,
    CONF_TRANSPORT,
    Transport,
)

from .conftest import TEST_PORT, TEST_SERIAL, FakeTransport, patch_client
from .test_config_flow import SERIAL_INPUT, TCP_INPUT


async def start_reconfigure(hass, config_entry, step: str):
    """Open the reconfigure flow and pick a transport."""
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


class TestSerialReconfigure:
    async def test_the_form_is_prefilled_from_the_entry(
        self, hass, config_entry, mock_client
    ):
        form = await start_reconfigure(hass, config_entry, "serial")

        defaults = {
            key.schema: key.default()
            for key in form["data_schema"].schema
            if key.default is not None
        }
        assert defaults[CONF_SERIAL_PORT] == TEST_PORT
        assert defaults[CONF_ADDRESS] == 1

    async def test_a_new_port_is_saved(self, hass, config_entry, mock_client):
        form = await start_reconfigure(hass, config_entry, "serial")

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {**SERIAL_INPUT, CONF_SERIAL_PORT: "/dev/ttyUSB7"}
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert config_entry.data[CONF_SERIAL_PORT] == "/dev/ttyUSB7"

    async def test_no_second_entry_is_created(self, hass, config_entry, mock_client):
        form = await start_reconfigure(hass, config_entry, "serial")
        await hass.config_entries.flow.async_configure(form["flow_id"], SERIAL_INPUT)
        await hass.async_block_till_done()

        assert len(hass.config_entries.async_entries()) == 1


class TestTransportSwitch:
    async def test_a_meter_can_move_from_rs485_to_a_gateway(
        self, hass, config_entry, mock_client
    ):
        form = await start_reconfigure(hass, config_entry, "tcp")

        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], TCP_INPUT
        )
        await hass.async_block_till_done()

        assert result["reason"] == "reconfigure_successful"
        assert config_entry.data[CONF_TRANSPORT] == Transport.TCP
        assert config_entry.data[CONF_HOST] == "192.0.2.10"
        assert config_entry.data[CONF_PORT] == 502


class TestIdentityCheck:
    """The serial number is the meter's identity when it reports one."""

    async def test_a_different_meter_is_refused(self, hass, config_entry, mock_client):
        other = FakeTransport()
        for offset, char in enumerate("Z9Y8X76"):
            other.words[0x5000 + offset] = ord(char)

        form = await start_reconfigure(hass, config_entry, "serial")
        with patch_client(return_value=other):
            result = await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "wrong_meter"
        assert result["description_placeholders"] == {
            "expected": TEST_SERIAL,
            "found": "Z9Y8X76",
        }

    async def test_the_entry_is_left_alone_when_refused(
        self, hass, config_entry, mock_client
    ):
        other = FakeTransport()
        for offset, char in enumerate("Z9Y8X76"):
            other.words[0x5000 + offset] = ord(char)

        form = await start_reconfigure(hass, config_entry, "serial")
        with patch_client(return_value=other):
            await hass.config_entries.flow.async_configure(
                form["flow_id"], {**SERIAL_INPUT, CONF_SERIAL_PORT: "/dev/ttyUSB7"}
            )

        assert config_entry.data[CONF_SERIAL_PORT] == TEST_PORT

    async def test_a_meter_that_lost_its_serial_number_is_refused(
        self, hass, config_entry, mock_client
    ):
        silent = FakeTransport()
        for offset in range(7):
            silent.words[0x5000 + offset] = 0

        form = await start_reconfigure(hass, config_entry, "serial")
        with patch_client(return_value=silent):
            result = await hass.config_entries.flow.async_configure(
                form["flow_id"], SERIAL_INPUT
            )

        assert result["reason"] == "wrong_meter"
        assert result["description_placeholders"]["found"] == "none"

    async def test_a_meter_without_a_serial_number_can_still_move_ports(
        self, hass, anonymous_entry
    ):
        # Nothing identifies such a meter but where it lives, and where it
        # lives is exactly what is being changed.
        anonymous = FakeTransport()
        for offset in range(7):
            anonymous.words.pop(0x5000 + offset, None)

        with patch_client(return_value=anonymous):
            await hass.config_entries.async_setup(anonymous_entry.entry_id)
            await hass.async_block_till_done()

            form = await start_reconfigure(hass, anonymous_entry, "serial")
            result = await hass.config_entries.flow.async_configure(
                form["flow_id"], {**SERIAL_INPUT, CONF_SERIAL_PORT: "/dev/ttyUSB7"}
            )
            await hass.async_block_till_done()

        assert result["reason"] == "reconfigure_successful"
        assert anonymous_entry.data[CONF_SERIAL_PORT] == "/dev/ttyUSB7"


class TestEntityContinuity:
    async def test_the_unique_id_and_entities_survive_a_port_change(
        self, hass, config_entry, mock_client
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        registry = er.async_get(hass)
        before = {e.entity_id for e in registry.entities.values()}
        assert before

        form = await start_reconfigure(hass, config_entry, "serial")
        await hass.config_entries.flow.async_configure(
            form["flow_id"], {**SERIAL_INPUT, CONF_SERIAL_PORT: "/dev/ttyUSB7"}
        )
        await hass.async_block_till_done()

        assert config_entry.unique_id == TEST_SERIAL
        assert {e.entity_id for e in registry.entities.values()} == before


@pytest.fixture
def anonymous_entry(hass):
    """An entry for a meter that never reported a serial number."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.carlo_gavazzi_em300.const import DOMAIN

    from .conftest import serial_config

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="EM340",
        unique_id=f"{TEST_PORT}:1",
        data={**serial_config(), "name": "EM340", "model": "EM340"},
    )
    entry.add_to_hass(hass)
    return entry
